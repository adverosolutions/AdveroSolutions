"""changesets/deliverability_2026_09_25: proadvero.com out, risky contacts off,
Microsoft-hosted leads parked in a list and back.

One httpx.MockTransport keeps campaigns, leads, lead lists and move jobs the
way the API does, so the tests see the exact calls a live run would send.
Like the live API (read 2026-09-25), no lead the fake returns carries a
``list_id`` field: list membership is only visible through leads/list
{list_id}, which the fake answers from its own private record.
"""
import copy
import json
import os

import httpx
import pytest

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
        out += [lead("ms%d" % n, cid), lead("mid%d" % n, cid, step=True), lead("ms%db" % n, cid),
                lead("g%d" % n, cid, esp=1), lead("rep%d" % n, cid, replies=1)]
    return out


PARKED = sorted(["ms%d" % n for n in range(6)] + ["mid%d" % n for n in range(6)] + ["ms%db" % n for n in range(6)])


def public(row):
    return dict((k, v) for k, v in row.items() if not k.startswith("_"))


class Fake(object):
    """``ignore_ids``: a move takes every lead of the source (the over-move
    the canary is there for). ``job_final``: what every job ends as.
    ``move_on_fail``: whether a failed/cancelled job still moved its leads.
    ``skip_restore``: a restore job reports success and moves nothing."""

    def __init__(self, leads=None, conflicts=0, strict_reads=False, ignore_ids=False,
                 job_final="success", move_on_fail=False, job_404=False, skip_restore=False):
        self.campaigns = dict(
            (cid, {"id": cid, "name": name, "status": 2, "allow_risky_contacts": True,
                   "email_list": list(D.RECORDED_EMAIL_LIST), "daily_limit": 50})
            for cid, name in D.CAMPAIGNS.items())
        self.leads = dict((l["id"], copy.deepcopy(l)) for l in (leads or workspace_leads()))
        self.lists = []
        self.jobs = {}
        self.conflicts = conflicts
        self.strict_reads = strict_reads
        self.ignore_ids = ignore_ids
        self.job_final = job_final
        self.move_on_fail = move_on_fail
        self.job_404 = job_404
        self.skip_restore = skip_restore
        self.fail_lead_reads = False
        self.requests = []
        self.moves = []            # (body, manifest ids at the time of the call)
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
            if self.fail_lead_reads:
                return httpx.Response(500, text="boom")
            rows = list(self.leads.values())
            if body.get("campaign"):
                rows = [r for r in rows if r.get("campaign") == body["campaign"]]
            if body.get("list_id"):
                rows = [r for r in rows if r.get("_list") == body["list_id"]]
            start = int(body.get("starting_after") or 0)
            page = rows[start:start + 4]            # small pages exercise the cursor
            nxt = str(start + 4) if start + 4 < len(rows) else None
            return httpx.Response(200, json={"items": [public(r) for r in page], "next_starting_after": nxt})
        if path.startswith("leads/") and m == "GET":
            lid = path.split("/", 1)[1]
            if lid not in self.leads:
                return httpx.Response(404, text="not found")
            return httpx.Response(200, json=public(self.leads[lid]))
        if path == "lead-lists":
            if m == "GET":
                q = request.url.params.get("search") or ""
                return httpx.Response(200, json={"items": [l for l in self.lists if q in l["name"]]})
            new = {"id": "list-%d" % (len(self.lists) + 1), "name": body["name"]}
            self.lists.append(new)
            return httpx.Response(200, json=new)
        if path == "leads/move":
            self.moves.append((body, self.manifest_probe() if self.manifest_probe else None))
            if self.conflicts:
                self.conflicts -= 1
                return httpx.Response(409, text="another move job is running")
            moved = []
            to_list = body.get("to_list_id")
            restoring = bool(body.get("to_campaign_id"))
            final = self.job_final
            act = final == "success" or (final in ("failed", "cancelled") and self.move_on_fail) \
                or final == "in-progress"
            if restoring and self.skip_restore:
                act = False
            if act:
                for row in self.leads.values():
                    in_src = (row.get("campaign") == body["campaign"]) if body.get("campaign") \
                        else (row.get("_list") == body.get("list_id"))
                    if not in_src or (row["id"] not in body["ids"] and not self.ignore_ids):
                        continue
                    if to_list:
                        row["campaign"], row["_list"] = None, to_list
                    else:
                        row["campaign"], row["_list"] = body["to_campaign_id"], None
                    moved.append(row)
            jid = "job-%d" % (len(self.jobs) + 1)
            self.jobs[jid] = {"polls": 0, "moved": moved}
            return httpx.Response(200, json={"id": jid, "status": "pending", "progress": 0})
        if path.startswith("background-jobs/"):
            if self.job_404:
                return httpx.Response(404, text="no such job")
            job = self.jobs[path.split("/", 1)[1]]
            job["polls"] += 1
            status = "in-progress" if job["polls"] == 1 or self.job_final == "in-progress" else self.job_final
            return httpx.Response(200, json={
                "id": path.split("/", 1)[1], "status": status, "progress": 100,
                "data": {"moved_leads": len(job["moved"]),
                         "moved_lead_emails": [r["email"] for r in job["moved"]]}})
        return httpx.Response(404, text="unexpected %s %s" % (m, path))

    @property
    def writes(self):
        return [r for r in self.requests if r.method != "GET" and not r.url.path.endswith("leads/list")]

    def client(self):
        return Instantly(api_key="test-key", transport=httpx.MockTransport(self), sleep=lambda s: None)


def run(fake, argv, tmp_path, sleeps=None, confirm=None, out=None):
    return D.main(argv, client=fake.client(), backup_dir=str(tmp_path / "backups"),
                  manifest_dir=str(tmp_path / "manifests"), mirror_dir=str(tmp_path / "mirror"),
                  confirm=confirm, sleep=(sleeps.append if sleeps is not None else (lambda s: None)),
                  out=(out.append if out is not None else (lambda m: None)))


def manifest(tmp_path):
    path = D.manifest_paths(str(tmp_path / "manifests"), dryrun=False)[1]
    return dict((r["lead_id"], r) for r in json.load(open(path))["rows"])


# --------------------------------------------------------------- selection
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


# ----------------------------------------------------------------- dry-run
def test_dry_run_sends_no_write_and_writes_only_the_dryrun_manifest(tmp_env, live_mode, tmp_path):
    fake = Fake(strict_reads=True)
    assert run(fake, [], tmp_path) == D.EXIT_OK
    assert fake.writes == []
    assert not os.path.exists(tmp_path / "backups")
    csv_path, json_path = D.manifest_paths(str(tmp_path / "manifests"), dryrun=True)
    assert "DRYRUN" in csv_path and os.path.exists(csv_path)
    assert os.path.exists(tmp_path / "mirror" / os.path.basename(csv_path))
    assert not os.path.exists(D.manifest_paths(str(tmp_path / "manifests"), dryrun=False)[1])
    rows = json.load(open(json_path))["rows"]
    assert sorted(r["lead_id"] for r in rows) == PARKED
    assert {r["campaign_id"] for r in rows} == set(CIDS)


# ---------------------------------------------------------------- refusals
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


def test_a_corrupt_manifest_refuses_before_any_write_and_is_not_overwritten(tmp_env, live_mode, tmp_path):
    fake = Fake()
    (tmp_path / "manifests").mkdir()
    path = D.manifest_paths(str(tmp_path / "manifests"), False)[1]
    broken = '{"meta": {}, "rows": [{"lead_id": "old-parked", "campaign_id": "x"}'
    open(path, "w").write(broken)
    assert run(fake, ["--apply", "--yes"], tmp_path) == D.EXIT_INVALID
    assert fake.writes == [] and open(path).read() == broken


def test_restore_cannot_be_combined_with_dry_run_apply_or_restore_leads(tmp_env, live_mode, tmp_path):
    fake = Fake()
    for extra in (["--dry-run"], ["--apply"], ["--restore-leads"]):
        argv = ["--restore", "x.json", "--campaign", "cleaning_trigger", "--yes"] + extra
        assert run(fake, argv, tmp_path) == D.EXIT_REFUSED
    assert run(fake, ["--limit", "1"], tmp_path) == D.EXIT_REFUSED
    assert fake.requests == []


# ------------------------------------------------------------- happy path
def test_apply_canary_first_manifest_before_moves_exact_bodies_and_rerun(tmp_env, live_mode, tmp_path):
    from jobs import inbox_inventory as INV
    fake = Fake()
    json_path = D.manifest_paths(str(tmp_path / "manifests"), dryrun=False)[1]
    fake.manifest_probe = lambda: ([r["lead_id"] for r in json.load(open(json_path))["rows"]]
                                   if os.path.exists(json_path) else None)
    assert run(fake, ["--apply", "--yes"], tmp_path) == D.EXIT_OK

    patches = [json.loads(r.content) for r in fake.requests if r.method == "PATCH"]
    assert len(patches) == 6
    assert all(set(b) == {"email_list", "allow_risky_contacts"} and b["allow_risky_contacts"] is False
               and sorted(b["email_list"]) == D.TARGET_EMAIL_LIST for b in patches)

    bodies = [b for b, _ in fake.moves]
    assert sorted(fake.moves[0][1]) == PARKED                 # manifest complete before the first move
    assert len(bodies[0]["ids"]) == 1                          # the canary
    assert all(set(b) == {"ids", "copy_leads", "campaign", "to_list_id", "limit"} for b in bodies)
    assert all(b["limit"] == len(b["ids"]) and b["copy_leads"] is False and b["to_list_id"] == "list-1"
               for b in bodies)
    assert sorted(i for b in bodies for i in b["ids"]) == PARKED
    rows = manifest(tmp_path)
    assert all(r["moved_at"] and r["verified_in_list"] is True and r["verified_not_in_campaign"] is True
               for r in rows.values())
    assert fake.leads["g0"]["campaign"] == CIDS[0] and fake.leads["rep0"]["campaign"] == CIDS[0]
    assert os.path.exists(tmp_path / "mirror" / os.path.basename(json_path))
    assert set(D.REMOVE) <= set(INV.load_quarantine())

    before = len(fake.writes)
    assert run(fake, ["--apply", "--yes"], tmp_path) == D.EXIT_OK
    assert fake.writes[before:] == []
    assert len(manifest(tmp_path)) == len(PARKED)


def test_quarantine_keeps_an_existing_entry(tmp_env, live_mode, tmp_path):
    from jobs import inbox_inventory as INV
    INV.quarantine_inbox(D.REMOVE[0], reason="earlier reason")
    since = INV.load_quarantine()[D.REMOVE[0]]["since"]
    assert run(Fake(), ["--apply", "--yes"], tmp_path) == D.EXIT_OK
    ledger = INV.load_quarantine()
    assert ledger[D.REMOVE[0]]["since"] == since and ledger[D.REMOVE[0]]["reason"] == "earlier reason"
    assert ledger[D.REMOVE[1]]["reason"] == D.QUARANTINE_REASON


def test_a_lead_that_changed_during_the_prompt_is_not_moved(tmp_env, live_mode, tmp_path):
    fake = Fake()

    def confirm(prompt):
        fake.leads["mid0"]["email_reply_count"] = 1
        fake.leads["ms1"]["status"] = -2
        return "yes"
    assert run(fake, ["--apply"], tmp_path, confirm=confirm) == D.EXIT_OK
    assert fake.leads["mid0"]["campaign"] == CIDS[0] and fake.leads["ms1"]["campaign"] == CIDS[1]
    rows = manifest(tmp_path)
    assert rows["mid0"]["skip_reason"] == "replied" and rows["ms1"]["skip_reason"] == "not_active"
    assert not rows["mid0"]["moved_at"] and "mid0" not in [i for b, _ in fake.moves for i in b["ids"]]


# ----------------------------------------------------------------- failures
def test_a_409_on_move_is_re_read_waited_and_retried_without_double_moving(tmp_env, live_mode, tmp_path):
    fake = Fake(conflicts=1)
    sleeps = []
    assert run(fake, ["--apply", "--yes"], tmp_path, sleeps=sleeps) == D.EXIT_OK
    assert D.CONFLICT_WAIT in sleeps
    bodies = [b for b, _ in fake.moves]
    assert bodies[0]["ids"] == bodies[1]["ids"]
    moved = [i for b in bodies[1:] for i in b["ids"]]
    assert sorted(moved) == PARKED


def test_an_over_move_on_the_canary_stops_and_restore_brings_everything_back(tmp_env, live_mode, tmp_path):
    fake = Fake(ignore_ids=True)
    out = []
    assert run(fake, ["--apply", "--yes"], tmp_path, out=out) == D.EXIT_API
    assert len(fake.moves) == 1 and len(fake.moves[0][0]["ids"]) == 1
    assert any("OVER-MOVE" in m and "CANARY" in m for m in out)
    rows = manifest(tmp_path)
    over = sorted(l for l, r in rows.items() if r["skip_reason"] == "over_moved_by_server")
    canary = fake.moves[0][0]["ids"][0]
    assert over == sorted(set(["ms0", "mid0", "ms0b", "g0", "rep0"]) - {canary})   # Google and replied too
    assert all(fake.leads[i]["campaign"] is None for i in over)
    fake.ignore_ids = False
    assert run(fake, ["--restore-leads", "--apply", "--yes"], tmp_path) == D.EXIT_OK
    assert all(fake.leads[i]["campaign"] == CIDS[0] for i in over + [canary])


@pytest.mark.parametrize("final,move_on_fail", [("failed", False), ("failed", True), ("cancelled", False),
                                                ("in-progress", False)])
def test_a_job_that_does_not_succeed_stops_the_run(tmp_env, live_mode, tmp_path, monkeypatch, final, move_on_fail):
    monkeypatch.setattr(D, "MAX_POLLS", 3)
    fake = Fake(job_final=final, move_on_fail=move_on_fail)
    assert run(fake, ["--apply", "--yes"], tmp_path) == D.EXIT_API
    assert len(fake.moves) == 1
    canary = fake.moves[0][0]["ids"][0]
    landed = fake.leads[canary]["campaign"] is None
    # stamped only when the read-back shows it out of the campaign and in the list
    assert bool(manifest(tmp_path)[canary]["moved_at"]) is landed
    # a re-run decides from live state: a lead that did land is not sent again
    fake.job_final = "success"
    assert run(fake, ["--apply", "--yes"], tmp_path) == D.EXIT_OK
    later = [i for b, _ in fake.moves[1:] for i in b["ids"]]
    assert (canary in later) is (not landed)
    assert manifest(tmp_path)[canary]["moved_at"]


def test_job_polling_gives_up_after_three_4xx(tmp_env, live_mode, tmp_path):
    fake = Fake(job_404=True)
    assert run(fake, ["--apply", "--yes"], tmp_path) == D.EXIT_API
    assert len([r for r in fake.requests if "background-jobs" in r.url.path]) == D.MAX_BAD_POLLS
    assert len(fake.moves) == 1


def test_a_failed_read_back_leaves_the_batch_unstamped(tmp_env, live_mode, tmp_path):
    fake = Fake()
    orig = fake.__call__

    def handler(request):
        resp = orig(request)
        if request.url.path.endswith("leads/move"):
            fake.fail_lead_reads = True
        return resp
    client = Instantly(api_key="k", transport=httpx.MockTransport(handler), sleep=lambda s: None)
    rc = D.main(["--apply", "--yes"], client=client, backup_dir=str(tmp_path / "backups"),
                manifest_dir=str(tmp_path / "manifests"), mirror_dir=str(tmp_path / "mirror"),
                sleep=lambda s: None, out=lambda m: None)
    assert rc == D.EXIT_API and len(fake.moves) == 1
    canary = fake.moves[0][0]["ids"][0]
    assert fake.leads[canary]["campaign"] is None and not manifest(tmp_path)[canary]["moved_at"]
    fake.fail_lead_reads = False
    assert run(fake, ["--apply", "--yes"], tmp_path) == D.EXIT_OK
    assert canary not in [i for b, _ in fake.moves[1:] for i in b["ids"]]
    assert manifest(tmp_path)[canary]["verified_in_list"] is True


def test_a_campaign_resumed_between_the_patches_and_the_moves_stops_the_moves(tmp_env, live_mode, tmp_path):
    fake = Fake()
    orig = fake.__call__

    def handler(request):
        if request.url.path.endswith("/lead-lists") and request.method == "POST":
            fake.campaigns[CIDS[0]]["status"] = 1          # resumed after A and B landed
        return orig(request)
    client = Instantly(api_key="k", transport=httpx.MockTransport(handler), sleep=lambda s: None)
    out = []
    rc = D.main(["--apply", "--yes"], client=client, backup_dir=str(tmp_path / "backups"),
                manifest_dir=str(tmp_path / "manifests"), mirror_dir=str(tmp_path / "mirror"),
                sleep=lambda s: None, out=out.append)
    assert rc == D.EXIT_API and fake.moves == []
    assert any("no longer 2 (paused)" in m for m in out)
    rows = manifest(tmp_path)
    assert sorted(rows) == PARKED and not any(r["moved_at"] for r in rows.values())

    # paused again, a re-run moves everything; a flip later (before campaign 3) stops there
    fake.campaigns[CIDS[0]]["status"] = 2
    calls = {"n": 0}

    def flip_later(request):
        if request.url.path.endswith("/leads/move"):
            calls["n"] += 1
            if calls["n"] == 3:
                fake.campaigns[CIDS[2]]["status"] = 1
        return orig(request)
    client = Instantly(api_key="k", transport=httpx.MockTransport(flip_later), sleep=lambda s: None)
    rc = D.main(["--apply", "--yes"], client=client, backup_dir=str(tmp_path / "backups"),
                manifest_dir=str(tmp_path / "manifests"), mirror_dir=str(tmp_path / "mirror"),
                sleep=lambda s: None, out=lambda m: None)
    assert rc == D.EXIT_API
    assert {b["campaign"] for b, _ in fake.moves} == {CIDS[0], CIDS[1]}
    rows = manifest(tmp_path)
    assert all(rows[i]["moved_at"] for i in rows if rows[i]["campaign_id"] in CIDS[:2])
    assert not any(rows[i]["moved_at"] for i in rows if rows[i]["campaign_id"] == CIDS[2])


# ------------------------------------------------------------------ restore
def test_restore_leads_groups_by_campaign_and_verifies(tmp_env, live_mode, tmp_path):
    fake = Fake()
    assert run(fake, ["--apply", "--yes"], tmp_path) == D.EXIT_OK
    n = len(fake.moves)
    assert run(fake, ["--restore-leads"], tmp_path) == D.EXIT_OK      # dry-run moves nothing
    assert len(fake.moves) == n
    assert run(fake, ["--restore-leads", "--apply", "--yes", "--limit", "1"], tmp_path) == D.EXIT_OK
    first_mid = [i for i in manifest_order(tmp_path) if i.startswith("mid")][0]
    assert [b["ids"] for b, _ in fake.moves[n:]] == [[first_mid]]     # --limit prefers mid-sequence
    assert run(fake, ["--restore-leads", "--apply", "--yes"], tmp_path) == D.EXIT_OK
    back = [b for b, _ in fake.moves[n + 1:]]
    assert [b["to_campaign_id"] for b in back] == CIDS
    assert all(set(b) == {"ids", "copy_leads", "list_id", "to_campaign_id", "limit"} for b in back)
    assert all(fake.leads[i]["campaign"] is not None for i in PARKED)
    assert all(r["restored_at"] for r in manifest(tmp_path).values())


def manifest_order(tmp_path):
    path = D.manifest_paths(str(tmp_path / "manifests"), dryrun=False)[1]
    return [r["lead_id"] for r in json.load(open(path))["rows"]]


def test_restore_that_moves_nothing_is_not_reported_restored(tmp_env, live_mode, tmp_path):
    fake = Fake(skip_restore=True)
    assert run(fake, ["--apply", "--yes"], tmp_path) == D.EXIT_OK
    assert run(fake, ["--restore-leads", "--apply", "--yes"], tmp_path) == D.EXIT_API
    assert not any(r["restored_at"] for r in manifest(tmp_path).values())


def test_restore_refuses_an_active_campaign(tmp_env, live_mode, tmp_path):
    fake = Fake()
    assert run(fake, ["--apply", "--yes"], tmp_path) == D.EXIT_OK
    n = len(fake.moves)
    fake.campaigns[CIDS[3]]["status"] = 1
    assert run(fake, ["--restore-leads", "--apply", "--yes"], tmp_path) == D.EXIT_INVALID
    assert len(fake.moves) == n


# ------------------------------------------------------------ round 2
def test_a_rerun_after_an_over_move_is_refused_until_restored(tmp_env, live_mode, tmp_path):
    fake = Fake(ignore_ids=True)
    assert run(fake, ["--apply", "--yes"], tmp_path) == D.EXIT_API
    n, writes = len(fake.moves), len(fake.writes)
    out = []
    assert run(fake, ["--apply", "--yes"], tmp_path, out=out) == D.EXIT_INVALID
    assert len(fake.moves) == n and len(fake.writes) == writes
    assert any(D.RESTORE_CMD in m for m in out) and any("REFUSED" in m for m in out)
    assert run(fake, ["--ack-over-move"], tmp_path) == D.EXIT_REFUSED          # only with --apply
    # the override is honoured (the fake still over-moves, so the canary stops it again)
    assert run(fake, ["--apply", "--yes", "--ack-over-move"], tmp_path) == D.EXIT_API
    assert len(fake.moves) == n + 1
    fake.ignore_ids = False
    assert run(fake, ["--restore-leads", "--apply", "--yes"], tmp_path) == D.EXIT_OK
    assert run(fake, ["--apply", "--yes"], tmp_path) == D.EXIT_OK
    assert fake.leads["g0"]["campaign"] == CIDS[0] and fake.leads["rep0"]["campaign"] == CIDS[0]
    assert all(fake.leads[i]["campaign"] is None for i in PARKED)


def test_the_canary_is_the_middle_eligible_lead(tmp_env, live_mode, tmp_path):
    fake = Fake()
    assert run(fake, ["--apply", "--yes"], tmp_path) == D.EXIT_OK
    eligible0 = [i for i in manifest_order(tmp_path) if i in PARKED and fake.leads[i]["_list"]
                 and manifest(tmp_path)[i]["campaign_id"] == CIDS[0]]
    assert fake.moves[0][0]["ids"] == [eligible0[len(eligible0) // 2]]


def test_selection_is_rechecked_before_every_batch(tmp_env, live_mode, tmp_path, monkeypatch):
    monkeypatch.setattr(D, "MOVE_BATCH", 1)
    fake = Fake()
    orig = fake.__call__
    calls = {"n": 0}

    def handler(request):
        if request.url.path.endswith("/leads/move"):
            calls["n"] += 1
            if calls["n"] == 2:
                fake.leads["ms0b"]["email_reply_count"] = 1
        return orig(request)
    client = Instantly(api_key="k", transport=httpx.MockTransport(handler), sleep=lambda s: None)
    rc = D.main(["--apply", "--yes"], client=client, backup_dir=str(tmp_path / "backups"),
                manifest_dir=str(tmp_path / "manifests"), mirror_dir=str(tmp_path / "mirror"),
                sleep=lambda s: None, out=lambda m: None)
    assert rc == D.EXIT_OK
    assert fake.leads["ms0b"]["campaign"] == CIDS[0] and manifest(tmp_path)["ms0b"]["skip_reason"] == "replied"


class Lagging(Fake):
    """leads/list answers from the state before the last move for a few calls."""

    def __init__(self, lag=3, **kw):
        Fake.__init__(self, **kw)
        self.lag, self.stale, self.lag_left = lag, None, 0

    def __call__(self, request):
        path = request.url.path[len("/api/v2/"):]
        if path == "leads/move":
            snap = copy.deepcopy(self.leads)
            resp = Fake.__call__(self, request)
            self.stale, self.lag_left = snap, self.lag
            return resp
        if path == "leads/list" and self.lag_left > 0:
            self.lag_left -= 1
            live, self.leads = self.leads, self.stale
            try:
                return Fake.__call__(self, request)
            finally:
                self.leads = live
        return Fake.__call__(self, request)


def test_a_lagging_index_gets_settle_reads_before_a_batch_is_unverified(tmp_env, live_mode, tmp_path):
    fake = Lagging()
    sleeps = []
    assert run(fake, ["--apply", "--yes"], tmp_path, sleeps=sleeps) == D.EXIT_OK
    assert D.SETTLE_WAIT in sleeps
    assert all(fake.leads[i]["campaign"] is None for i in PARKED)
    stuck = Lagging(lag=10 ** 6)
    assert run(stuck, ["--apply", "--yes"], tmp_path / "stuck") == D.EXIT_API
    assert len(stuck.moves) == 1


def test_restore_prints_stages_and_stops_when_a_campaign_is_resumed(tmp_env, live_mode, tmp_path):
    fake = Fake()
    assert run(fake, ["--apply", "--yes"], tmp_path) == D.EXIT_OK
    n = len(fake.moves)
    orig = fake.__call__

    def handler(request):
        resp = orig(request)
        if request.url.path.endswith("/leads/move"):
            fake.campaigns[CIDS[1]]["status"] = 1
        return resp
    client = Instantly(api_key="k", transport=httpx.MockTransport(handler), sleep=lambda s: None)
    out = []
    rc = D.main(["--restore-leads", "--apply", "--yes"], client=client, backup_dir=str(tmp_path / "backups"),
                manifest_dir=str(tmp_path / "manifests"), mirror_dir=str(tmp_path / "mirror"),
                sleep=lambda s: None, out=out.append)
    assert rc == D.EXIT_API and len(fake.moves) == n + 1
    assert any("stage=mid_sequence" in m for m in out) and any("no longer 2 (paused)" in m for m in out)
    rows = manifest(tmp_path)
    assert all(bool(r["restored_at"]) is (r["campaign_id"] == CIDS[0]) for r in rows.values())
