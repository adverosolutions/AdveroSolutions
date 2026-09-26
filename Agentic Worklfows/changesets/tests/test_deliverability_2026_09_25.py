"""changesets/deliverability_2026_09_25: proadvero.com out, risky contacts off,
Microsoft-hosted leads parked in a list and back.

One httpx.MockTransport keeps campaigns, leads, lead lists and move jobs the
way the API does, so the tests see the exact calls a live run would send.
"""
import copy
import json
import os

import httpx

from shared.instantly import Instantly
from changesets.deliverability_2026_09_25 import apply_deliverability as D

CIDS = list(D.CAMPAIGNS)


def lead(lid, cid, status=1, esp=2, replies=0, step=False, **extra):
    row = {"id": lid, "campaign": cid, "email": "%s@example.com" % lid, "status": status,
           "esp_code": esp, "email_reply_count": replies, "first_name": "F", "company_name": "Co"}
    if step:
        row["status_summary"] = {"lastStep": {"from": "lorenzo@adveromedia.com", "stepID": "0_1_0",
                                              "timestamp_executed": "2026-09-15T16:22:40.861Z"}}
    row.update(extra)
    return row


def workspace_leads():
    out = []
    for n, cid in enumerate(CIDS):
        out += [lead("ms%d" % n, cid), lead("mid%d" % n, cid, step=True),
                lead("g%d" % n, cid, esp=1), lead("rep%d" % n, cid, replies=1)]
    return out


class Fake(object):
    def __init__(self, campaigns=None, leads=None, conflicts=0, strict_reads=False):
        self.campaigns = campaigns or dict(
            (cid, {"id": cid, "name": name, "status": 2, "allow_risky_contacts": True,
                   "email_list": list(D.RECORDED_EMAIL_LIST), "daily_limit": 50})
            for cid, name in D.CAMPAIGNS.items())
        self.leads = dict((l["id"], copy.deepcopy(l)) for l in (leads or workspace_leads()))
        self.lists = []
        self.jobs = {}
        self.conflicts = conflicts
        self.strict_reads = strict_reads
        self.requests = []
        self.moves = []            # (body, manifest_existed)
        self.manifest_probe = None

    def __call__(self, request):
        self.requests.append(request)
        m, path = request.method, request.url.path[len("/api/v2/"):]
        body = json.loads(request.content) if request.content else {}
        if self.strict_reads and m != "GET" and path != "leads/list":
            raise AssertionError("dry-run sent a write: %s %s" % (m, path))
        if path.startswith("campaigns/"):
            cid = path.split("/", 1)[1]
            if m == "PATCH":
                self.campaigns[cid].update(body)
            return httpx.Response(200, json=self.campaigns[cid])
        if path == "leads/list":
            rows = list(self.leads.values())
            if body.get("campaign"):
                rows = [r for r in rows if r.get("campaign") == body["campaign"]]
            if body.get("list_id"):
                rows = [r for r in rows if r.get("list_id") == body["list_id"]]
            start = int(body.get("starting_after") or 0)
            page = rows[start:start + 2]            # tiny pages exercise the cursor
            nxt = str(start + 2) if start + 2 < len(rows) else None
            return httpx.Response(200, json={"items": page, "next_starting_after": nxt})
        if path.startswith("leads/") and m == "GET":
            lid = path.split("/", 1)[1]
            if lid not in self.leads:
                return httpx.Response(404, text="not found")
            return httpx.Response(200, json=self.leads[lid])
        if path == "lead-lists":
            if m == "GET":
                q = request.url.params.get("search") or ""
                return httpx.Response(200, json={"items": [l for l in self.lists if q in l["name"]]})
            new = {"id": "list-%d" % (len(self.lists) + 1), "name": body["name"]}
            self.lists.append(new)
            return httpx.Response(200, json=new)
        if path == "leads/move":
            if self.manifest_probe:
                self.moves.append((body, self.manifest_probe()))
            else:
                self.moves.append((body, None))
            if self.conflicts:
                self.conflicts -= 1
                return httpx.Response(409, text="another move job is running")
            for lid in body["ids"]:
                row = self.leads[lid]
                if body.get("campaign") and row.get("campaign") != body["campaign"]:
                    continue
                if body.get("list_id") and row.get("list_id") != body["list_id"]:
                    continue
                if body.get("to_list_id"):
                    row["campaign"], row["list_id"] = None, body["to_list_id"]
                else:
                    row["campaign"], row["list_id"] = body["to_campaign_id"], None
            jid = "job-%d" % (len(self.jobs) + 1)
            self.jobs[jid] = 0
            return httpx.Response(200, json={"id": jid, "status": "pending", "progress": 0})
        if path.startswith("background-jobs/"):
            jid = path.split("/", 1)[1]
            self.jobs[jid] += 1
            return httpx.Response(200, json={"id": jid, "status": "in-progress" if self.jobs[jid] == 1
                                             else "success", "progress": 100})
        return httpx.Response(404, text="unexpected %s %s" % (m, path))

    @property
    def writes(self):
        return [r for r in self.requests if r.method != "GET" and not r.url.path.endswith("leads/list")]

    def client(self):
        return Instantly(api_key="test-key", transport=httpx.MockTransport(self), sleep=lambda s: None)


def run(fake, argv, tmp_path, sleeps=None):
    return D.main(argv, client=fake.client(), backup_dir=str(tmp_path / "backups"),
                  manifest_dir=str(tmp_path / "manifests"),
                  sleep=(sleeps.append if sleeps is not None else (lambda s: None)), out=lambda m: None)


def test_lead_selection_filter():
    c0, c1 = CIDS[0], CIDS[1]
    leads = [
        lead("ok", c0), lead("okmid", c1, step=True), lead("ok", c0),        # duplicate id counted once
        lead("google", c0, esp=1), lead("other", c0, esp=999),
        lead("paused", c0, status=2), lead("done", c0, status=3), lead("bounced", c0, status=-1),
        lead("replied", c0, replies=2), lead("noreplyfield", c0, email_reply_count=None),
        lead("interested", c0, lt_interest_status=1), lead("ooo", c0, lt_interest_status=0),
        lead("elsewhere", "11111111-0000-0000-0000-000000000000"), lead("nocampaign", None),
    ]
    picked, excluded = D.select_leads(leads)
    assert [l["id"] for l in picked] == ["noreplyfield", "ok", "okmid"]
    assert excluded == {"not_microsoft": 2, "not_active": 3, "replied": 1, "interest_set": 2}
    assert D.stage_of(picked[2]) == "mid_sequence" and D.stage_of(picked[1]) == "not_started"


def test_dry_run_sends_no_write_and_writes_only_the_dryrun_manifest(tmp_env, live_mode, tmp_path):
    fake = Fake(strict_reads=True)
    assert run(fake, [], tmp_path) == D.EXIT_OK
    assert fake.writes == []
    assert not os.path.exists(tmp_path / "backups")
    csv_path, json_path = D.manifest_paths(str(tmp_path / "manifests"), dryrun=True)
    assert "DRYRUN" in csv_path and os.path.exists(csv_path)
    assert not os.path.exists(D.manifest_paths(str(tmp_path / "manifests"), dryrun=False)[1])
    rows = json.load(open(json_path))["rows"]
    assert sorted(r["lead_id"] for r in rows) == sorted(["ms%d" % n for n in range(6)] + ["mid%d" % n for n in range(6)])
    assert {r["campaign_id"] for r in rows} == set(CIDS)
    assert {r["stage"] for r in rows if r["lead_id"].startswith("mid")} == {"mid_sequence"}


def test_email_list_drift_is_refused_before_any_write(tmp_env, live_mode, tmp_path):
    fake = Fake()
    fake.campaigns[CIDS[2]]["email_list"] = D.RECORDED_EMAIL_LIST[:-1]
    assert run(fake, ["--apply", "--yes"], tmp_path) == D.EXIT_INVALID
    assert fake.writes == []


def test_a_campaign_that_is_not_paused_is_refused(tmp_env, live_mode, tmp_path):
    fake = Fake()
    fake.campaigns[CIDS[4]]["status"] = 1
    assert run(fake, ["--apply", "--yes"], tmp_path) == D.EXIT_INVALID
    assert fake.writes == []


def test_apply_writes_the_manifest_before_the_first_move_and_verifies(tmp_env, live_mode, tmp_path):
    from jobs import inbox_inventory as INV
    fake = Fake()
    json_path = D.manifest_paths(str(tmp_path / "manifests"), dryrun=False)[1]

    def probe():
        if not os.path.exists(json_path):
            return None
        return [r["lead_id"] for r in json.load(open(json_path))["rows"]]
    fake.manifest_probe = probe
    assert run(fake, ["--apply", "--yes"], tmp_path) == D.EXIT_OK

    # the manifest held every planned lead before the first move call
    first_body, manifest_then = fake.moves[0]
    assert manifest_then is not None and len(manifest_then) == 12
    # one move per campaign, from that campaign, to the parked list
    assert [b["campaign"] for b, _ in fake.moves] == CIDS
    assert all(b["to_list_id"] == "list-1" and b["copy_leads"] is False for b, _ in fake.moves)
    for cid, camp in fake.campaigns.items():
        assert sorted(camp["email_list"]) == D.TARGET_EMAIL_LIST and camp["allow_risky_contacts"] is False
    assert len(os.listdir(tmp_path / "backups")) == 6
    assert set(D.REMOVE) <= set(INV.load_quarantine())
    rows = json.load(open(json_path))["rows"]
    assert all(r["verified_in_list"] is True and r["verified_not_in_campaign"] is True and r["moved_at"]
               for r in rows)
    assert fake.leads["g0"]["campaign"] == CIDS[0] and fake.leads["rep0"]["campaign"] == CIDS[0]

    # a re-run changes nothing: campaigns already applied, no lead left to park
    before = len(fake.writes)
    assert run(fake, ["--apply", "--yes"], tmp_path) == D.EXIT_OK
    assert [r.method for r in fake.writes[before:]] == []
    assert len(json.load(open(json_path))["rows"]) == 12


def test_a_409_on_move_is_re_read_waited_and_retried_without_double_moving(tmp_env, live_mode, tmp_path):
    fake = Fake(conflicts=1)
    sleeps = []
    assert run(fake, ["--apply", "--yes"], tmp_path, sleeps=sleeps) == D.EXIT_OK
    assert D.CONFLICT_WAIT in sleeps
    bodies = [b for b, _ in fake.moves]
    assert bodies[0]["ids"] == bodies[1]["ids"]          # the refused batch is sent again once
    moved = [i for b in bodies[1:] for i in b["ids"]]
    assert len(moved) == len(set(moved)) == 12


def test_restore_leads_groups_by_original_campaign(tmp_env, live_mode, tmp_path):
    fake = Fake()
    assert run(fake, ["--apply", "--yes"], tmp_path) == D.EXIT_OK
    n = len(fake.moves)
    assert run(fake, ["--restore-leads"], tmp_path) == D.EXIT_OK      # dry-run moves nothing
    assert len(fake.moves) == n
    assert run(fake, ["--restore-leads", "--apply", "--yes"], tmp_path) == D.EXIT_OK
    back = [b for b, _ in fake.moves[n:]]
    assert [b["to_campaign_id"] for b in back] == CIDS
    assert all(b["list_id"] == "list-1" and "campaign" not in b for b in back)
    for b in back:
        assert sorted(b["ids"]) == sorted(i for i in b["ids"] if fake.leads[i]["campaign"] == b["to_campaign_id"])
        assert len(b["ids"]) == 2
    assert all(fake.leads["ms%d" % k]["campaign"] == CIDS[k] for k in range(6))
