"""Regression tests for the reviewer-max re-review of the change-sets (2026-09-22).

Each test is one of the reviewer's probes (review-d2/p1..p9) or one of the ten
defects, turned into an assertion on the exact requests that would be sent.
Every Instantly call is an httpx.MockTransport; nothing leaves the process.
"""
import copy
import json
import os
from datetime import timedelta

import httpx
import pytest

from shared import job_log
from shared.instantly import Instantly
from changesets import rollback as R
from changesets import instantly_webhooks as cw
from changesets.capacity import apply_capacity as cap
from changesets.capacity import apply_promotion as ap
from changesets.inbox_actions import apply_inbox_actions as A
from changesets.instantly_phase0 import apply_instantly_phase0 as P0
from changesets.tests.test_capacity_and_rollback import (
    CR, LIVE, NEW, NOW, STAMP, FakeInstantly, account, plan_file, promo_record, write_cs, action)

TARGET = "https://advero--advero-reply-engine-web.modal.run/webhooks/instantly"


def _cap(fake, argv, tmp_path, now=NOW, confirm=None, client=None):
    out = []
    code = cap.main(argv, client=client or fake.client(), now=now, out=out.append,
                    backup_dir=str(tmp_path / "backups"), dryrun_dir=str(tmp_path / "dry"), confirm=confirm)
    return code, out


def _files(tmp_path):
    d = tmp_path / "backups"
    return sorted(os.listdir(str(d))) if d.exists() else []


# ============================================= defect 1: stale confirmation
def test_p1_capacity_refuses_when_the_list_moves_while_the_prompt_is_open(tmp_env, live_mode, tmp_path):
    fake = FakeInstantly(accounts=[account(e) for e in LIVE + NEW + ["promo@d9.com"]])

    def confirm(_prompt):
        fake.campaigns[CR]["email_list"] = ["promo@d9.com", "a2@d1.com", "b1@d2.com"]
        return "cleaning_reactivation"

    code, out = _cap(fake, ["--input", plan_file(tmp_path, limits={"cleaning_reactivation": 100}),
                            "--campaign", "cleaning_reactivation", "--apply"], tmp_path, confirm=confirm)
    assert code == cap.EXIT_REFUSED
    assert fake.writes == []
    assert _files(tmp_path) == []
    text = "\n".join(out)
    assert "changed while the confirmation was open" in text
    assert "removes a1@d1.com; adds promo@d9.com" in text
    assert fake.campaigns[CR]["email_list"] == ["promo@d9.com", "a2@d1.com", "b1@d2.com"]


def test_p1_capacity_uses_the_post_confirmation_read_as_the_before_image(tmp_env, live_mode, tmp_path):
    fake = FakeInstantly()

    def confirm(_prompt):
        fake.campaigns[CR]["pl_value"] = 1234       # an unrelated field moves: still safe to apply
        return "cleaning_reactivation"

    code, out = _cap(fake, ["--input", plan_file(tmp_path, limits={"cleaning_reactivation": 100}),
                            "--campaign", "cleaning_reactivation", "--apply"], tmp_path, confirm=confirm)
    assert code == 0, out
    assert [(r.method, r.url.path) for r in fake.requests] == [
        ("GET", "/api/v2/accounts"), ("GET", "/api/v2/campaigns/%s" % CR),
        ("GET", "/api/v2/campaigns/%s" % CR), ("PATCH", "/api/v2/campaigns/%s" % CR)]
    point = json.loads((tmp_path / "backups" / ("capacity_%s_%s.json" % (CR, STAMP))).read_text())
    assert point["pl_value"] == 1234                           # the fresh read
    assert point["_rollback_point"]["after"] == {"email_list": LIVE + NEW, "daily_limit": 100}


def test_p2_promotion_refuses_when_the_list_moves_while_the_prompt_is_open(tmp_env, live_mode, tmp_path, capsys):
    fake = FakeInstantly(accounts=[account(e) for e in LIVE + NEW + ["cap1@d5.com"]])

    def confirm(_prompt):
        fake.campaigns[CR]["email_list"] = LIVE + ["cap1@d5.com"]
        return "yes"

    code = ap.main(["--changeset", promo_record(tmp_path), "--apply"], client=fake.client(), now=NOW,
                   backup_dir=str(tmp_path / "backups"), dryrun_dir=str(tmp_path / "dry"), confirm=confirm)
    assert code == ap.EXIT_REFUSED
    assert fake.writes == [] and _files(tmp_path) == []
    assert "adds cap1@d5.com" in capsys.readouterr().err
    assert "cap1@d5.com" in fake.campaigns[CR]["email_list"]


# ============================================= defect 2: late-landing 504
def test_p9_a_504_that_lands_after_the_re_read_still_leaves_a_restorable_point(tmp_env, live_mode, tmp_path):
    fake = FakeInstantly()
    pending = {}

    def handler(req):
        if req.method == "PATCH" and not pending.get("sent"):
            fake.requests.append(req)
            pending["body"] = json.loads(req.content)
            pending["sent"] = True
            return httpx.Response(504, text="gateway timeout")
        resp = fake(req)
        if req.method == "GET" and req.url.path.endswith(CR) and pending.get("body") and not pending.get("landed"):
            fake.campaigns[CR].update(pending["body"])           # lands AFTER this read answered
            pending["landed"] = True
        return resp

    client = Instantly(api_key="k", transport=httpx.MockTransport(handler), sleep=lambda s: None)
    plan = plan_file(tmp_path, limits={"cleaning_reactivation": 100})
    argv = ["--input", plan, "--campaign", "cleaning_reactivation", "--apply", "--yes"]
    code, out = _cap(fake, argv, tmp_path, client=client)
    assert code == cap.EXIT_API
    point = tmp_path / "backups" / ("capacity_%s_%s.json" % (CR, STAMP))
    assert _files(tmp_path) == [point.name]                    # unsuffixed, restorable
    assert json.loads(point.read_text())["_rollback_point"]["outcome"] in ("unchanged_at_reread",
                                                                          "unknown_after_error")
    # the write landed later; a re-run sees a match and writes nothing
    assert fake.campaigns[CR]["daily_limit"] == 100
    code, out = _cap(fake, argv, tmp_path, now=NOW + timedelta(minutes=5), client=client)
    assert code == 0 and "live already matches" in "\n".join(out)
    assert _files(tmp_path) == [point.name]
    # and the only before-image restores
    n = len(fake.requests)
    code, out = _cap(fake, ["--restore", str(point), "--campaign", "cleaning_reactivation", "--yes"],
                     tmp_path, now=NOW + timedelta(minutes=9), client=client)
    assert code == 0, out
    assert [json.loads(r.content) for r in fake.requests[n:] if r.method == "PATCH"] == [
        {"daily_limit": 50, "email_list": LIVE}]


def test_an_error_whose_re_read_shows_nothing_is_a_no_op_restore(tmp_env, live_mode, tmp_path):
    fake = FakeInstantly(fail_patch={CR: (504, False)})
    code, _out = _cap(fake, ["--input", plan_file(tmp_path, limits={"cleaning_reactivation": 100}),
                             "--campaign", "cleaning_reactivation", "--apply", "--yes"], tmp_path)
    assert code == cap.EXIT_API
    point = tmp_path / "backups" / ("capacity_%s_%s.json" % (CR, STAMP))
    n = len(fake.requests)
    code, out = _cap(fake, ["--restore", str(point), "--campaign", "cleaning_reactivation", "--yes"], tmp_path)
    assert code == 0 and "already matches" in "\n".join(out)
    assert [r.method for r in fake.requests[n:]] == ["GET"]


# ========================= defect 3: restore reads first, refuses later changes
def _capacity_then_burned_removal(tmp_path):
    fake = FakeInstantly()
    bdir = tmp_path / "backups"
    code, _ = _cap(fake, ["--input", plan_file(tmp_path, limits={"cleaning_reactivation": 100}),
                          "--campaign", "cleaning_reactivation", "--apply", "--yes"], tmp_path)
    assert code == 0
    point = bdir / ("capacity_%s_%s.json" % (CR, STAMP))
    before = sorted(fake.campaigns[CR]["email_list"])
    write_cs(tmp_path, [dict(action(CR, "cleaning_reactivation", before=before))],
             pid="remove_from_email_list:a1@d1.com")
    out = []
    assert A.main(["--apply", "--id", "remove_from_email_list:a1@d1.com", "--yes", "--backup-dir", str(bdir)],
                  client=fake.client(), out=out.append, now=NOW + timedelta(days=2),
                  directory=tmp_path / "cs") == 0, out
    assert "a1@d1.com" not in fake.campaigns[CR]["email_list"]
    return fake, point


def test_p3_restore_refuses_to_undo_a_later_burned_inbox_removal(tmp_env, live_mode, tmp_path):
    fake, point = _capacity_then_burned_removal(tmp_path)
    printed_before_prompt = []
    out = []

    def confirm(_prompt):
        printed_before_prompt.extend(out)
        return "cleaning_reactivation"

    n = len(fake.requests)
    code = cap.main(["--restore", str(point), "--campaign", "cleaning_reactivation"], client=fake.client(),
                    now=NOW + timedelta(days=3), out=out.append, backup_dir=str(tmp_path / "backups"),
                    confirm=confirm)
    assert code == cap.EXIT_REFUSED
    assert [r.method for r in fake.requests[n:]] == ["GET"]           # read, never wrote
    assert "a1@d1.com" not in fake.campaigns[CR]["email_list"]
    text = "\n".join(out)
    assert "CHANGED SINCE THE APPLY: email_list" in text and "removes a1@d1.com" in text
    assert "--override-later-changes" in text
    assert printed_before_prompt == []                                # refused before any prompt
    assert not any(f.endswith(".prerestore.json") and f.startswith("capacity_") for f in _files(tmp_path))


def test_p3_the_override_restores_and_the_diff_is_printed_before_the_prompt(tmp_env, live_mode, tmp_path):
    fake, point = _capacity_then_burned_removal(tmp_path)
    out = []
    seen = []

    def confirm(_prompt):
        seen.extend(out)
        return "cleaning_reactivation"

    n = len(fake.requests)
    code = cap.main(["--restore", str(point), "--campaign", "cleaning_reactivation", "--override-later-changes"],
                    client=fake.client(), now=NOW + timedelta(days=3), out=out.append,
                    backup_dir=str(tmp_path / "backups"), confirm=confirm)
    assert code == 0, out
    before_prompt = "\n".join(seen)
    assert "would change: email_list 4 -> 3 inboxes; removes n1@d3.com, n2@d3.com; adds a1@d1.com" in before_prompt
    assert "would change: daily_limit 100 -> 50" in before_prompt
    assert [r.method for r in fake.requests[n:]] == ["GET", "GET", "PATCH"]
    assert json.loads(fake.requests[-1].content) == {"daily_limit": 50, "email_list": LIVE}


def test_restoring_an_older_point_over_a_newer_apply_is_refused(tmp_env, live_mode, tmp_path):
    fake = FakeInstantly(accounts=[account(e) for e in LIVE + NEW + ["x1@d8.com"]])
    first = plan_file(tmp_path, limits={"cleaning_reactivation": 100})
    assert _cap(fake, ["--input", first, "--campaign", "cleaning_reactivation", "--apply", "--yes"], tmp_path)[0] == 0
    doc = json.loads(open(first).read())
    doc["campaigns"]["cleaning_reactivation"]["add_inboxes"] = NEW + ["x1@d8.com"]
    doc["campaigns"]["cleaning_reactivation"]["daily_limit"] = 120
    doc["expected_total_daily_limit"] = 120
    second = str(tmp_path / "plan2.json")
    open(second, "w").write(json.dumps(doc))
    assert _cap(fake, ["--input", second, "--campaign", "cleaning_reactivation", "--apply", "--yes"], tmp_path,
                now=NOW + timedelta(hours=1))[0] == 0
    older = tmp_path / "backups" / ("capacity_%s_%s.json" % (CR, STAMP))
    n = len(fake.requests)
    code, out = _cap(fake, ["--restore", str(older), "--campaign", "cleaning_reactivation", "--yes"], tmp_path,
                     now=NOW + timedelta(hours=2))
    assert code == cap.EXIT_REFUSED
    assert [r.method for r in fake.requests[n:]] == ["GET"]


def test_every_restore_reads_before_it_prompts(tmp_env, live_mode, tmp_path):
    """Prompt order for the promotion, inbox-action and phase0 restores."""
    fake = FakeInstantly()
    assert ap.main(["--changeset", promo_record(tmp_path), "--apply", "--yes"], client=fake.client(), now=NOW,
                   backup_dir=str(tmp_path / "backups"), dryrun_dir=str(tmp_path / "dry")) == 0
    point = tmp_path / "backups" / ("promotion_%s_%s.json" % (CR, STAMP))
    reads_at_prompt = []

    def confirm(_prompt):
        reads_at_prompt.append(len([r for r in fake.requests if r.method == "GET"]))
        return "cleaning_reactivation"

    gets_before = len([r for r in fake.requests if r.method == "GET"])
    assert ap.main(["--restore", str(point), "--campaign", "cleaning_reactivation"], client=fake.client(),
                   now=NOW + timedelta(hours=1), backup_dir=str(tmp_path / "backups"), confirm=confirm) == 0
    assert reads_at_prompt == [gets_before + 1]
    assert fake.campaigns[CR]["email_list"] == LIVE


# ======================== defect 4: missing email_list, partial restore
def test_p5_a_live_read_without_email_list_is_refused(tmp_env, live_mode, tmp_path):
    fake = FakeInstantly()
    del fake.campaigns[CR]["email_list"]
    code, out = _cap(fake, ["--input", plan_file(tmp_path, limits={"cleaning_reactivation": 100}),
                            "--campaign", "cleaning_reactivation", "--apply", "--yes"], tmp_path)
    assert code == cap.EXIT_INVALID
    assert fake.writes == [] and _files(tmp_path) == []
    assert any("carries no email_list list" in l for l in out)


def test_p5_promotion_refuses_a_read_without_email_list(tmp_env, live_mode, tmp_path, capsys):
    fake = FakeInstantly()
    del fake.campaigns[CR]["email_list"]
    assert ap.main(["--changeset", promo_record(tmp_path), "--apply", "--yes"], client=fake.client(), now=NOW,
                   backup_dir=str(tmp_path / "backups"), dryrun_dir=str(tmp_path / "dry")) == ap.EXIT_INVALID
    assert fake.writes == []


def test_a_restore_that_cannot_put_back_every_field_is_partial(tmp_env, live_mode, tmp_path):
    fake = FakeInstantly()
    camp = dict(fake.campaigns[CR])
    del camp["email_list"]                                  # the before-image lacks one field
    point = R.write_point(str(tmp_path), "capacity_%s_x" % CR,
                          R.build_point("capacity", "apply", camp, ["daily_limit", "email_list"], NOW, CR,
                                        after={"daily_limit": 100, "email_list": LIVE + NEW}))
    fake.campaigns[CR].update({"daily_limit": 100, "email_list": LIVE + NEW})
    code, out = _cap(fake, ["--restore", point, "--campaign", "cleaning_reactivation", "--yes"], tmp_path)
    assert code == cap.EXIT_API
    assert [json.loads(r.content) for r in fake.writes] == [{"daily_limit": 50}]
    text = "\n".join(out)
    assert "PARTIAL" in text and "email_list" in text
    assert fake.campaigns[CR]["email_list"] == LIVE + NEW


# ================================== defect 5: equality on the restore side
def test_p6_an_additive_change_is_not_mistaken_for_already_restored(tmp_env, live_mode, tmp_path):
    seq_before = [{"steps": [{"type": "email", "delay": 3, "variants": [
        {"subject": "A", "body": "<div>a</div>"}, {"subject": "B", "body": "<div>b</div>"}]}]}]
    seq_after = copy.deepcopy(seq_before)
    seq_after[0]["steps"][0]["variants"][1]["v_disabled"] = True
    fake = FakeInstantly(campaigns={CR: {"id": CR, "name": "CR", "status": 1, "email_list": ["a1@d1.com"],
                                         "daily_limit": 50, "sequences": copy.deepcopy(seq_before)}})
    bdir = str(tmp_path / "backups")
    pre = R.write_point(bdir, "phase0_%s_x" % CR,
                        R.build_point("phase0", R.KIND_PREAPPLY, fake.campaigns[CR], ["sequences"], NOW, CR,
                                      "cleaning_reactivation", after={"sequences": seq_after}))
    settled = R.patch_and_settle(fake.client(), CR, {"sequences": seq_after}, pre, {"sequences": seq_before})
    assert settled["ok"]
    out = []
    n = len(fake.requests)
    code, info = R.restore(fake.client(), "phase0", settled["path"], CR, "cleaning_reactivation", bdir,
                           "phase0_%s_y" % CR, NOW, out.append)
    assert code == 0 and info["outcome"] == "restored_verified"
    writes = [r for r in fake.requests[n:] if r.method != "GET"]
    assert [json.loads(r.content) for r in writes] == [{"sequences": seq_before}]
    assert "v_disabled" not in fake.campaigns[CR]["sequences"][0]["steps"][0]["variants"][1]
    assert R.differing({"email_list": ["A@x.com", "b@y.com"]}, {"email_list": ["b@y.com", "a@x.com"]}) == []


# ======================================== defects 6 and 7: webhook rollback
def _webhook_client(live):
    reqs = []

    def handler(r):
        reqs.append(r)
        if r.method == "GET":
            return httpx.Response(200, json=live)
        return httpx.Response(200, json={"id": r.url.path.rsplit("/", 1)[1]})

    return Instantly(api_key="k", transport=httpx.MockTransport(handler), sleep=lambda s: None), reqs


def test_while_delete_is_unverified_rollback_sends_no_delete_and_fails(tmp_env, live_mode, tmp_path, capsys):
    assert cw.DELETE_WEBHOOK_VERIFIED is False
    bdir = str(tmp_path / "backups")
    cw.save_ledger([{"id": "w1", "event_type": "reply_received"}], bdir)
    client, reqs = _webhook_client([{"id": "w1", "event_type": "reply_received", "target_hook_url": TARGET,
                                     "name": "advero-reply-engine reply_received"}])
    code = cw.main(["--rollback", "--yes"], reader=lambda p: "rollback", client=client, backup_dir=bdir)
    out = capsys.readouterr().out
    assert code == 3
    assert [r.method for r in reqs] == ["GET"]
    assert "NOT deleted: w1" in out and "Settings > Webhooks" in out
    rows = open(str(job_log.job_log_path())).read()
    assert "changesets.instantly_webhooks,errors" in rows
    assert not cw.load_ledger(bdir)[0].get("deleted_at")


def test_p7_a_recorded_webhook_that_was_renamed_or_has_no_name_is_reported_not_kept(
        tmp_env, live_mode, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cw, "DELETE_WEBHOOK_VERIFIED", True)
    bdir = str(tmp_path / "backups")
    cw.save_ledger([{"id": "w1", "event_type": "reply_received"},
                    {"id": "w2", "event_type": "lead_interested"}], bdir)
    live = [{"id": "w1", "event_type": "reply_received", "target_hook_url": TARGET},
            {"id": "w2", "event_type": "lead_interested", "target_hook_url": TARGET, "name": "renamed in UI"}]
    client, reqs = _webhook_client(live)
    code = cw.main(["--rollback", "--yes"], reader=lambda p: "rollback", client=client, backup_dir=bdir)
    out = capsys.readouterr().out
    assert code == 3
    assert [r.method for r in reqs] == ["GET"]              # nothing deletable by the AND rule
    assert "w1: NOT deleted" in out and "w2: NOT deleted" in out
    assert "changesets.instantly_webhooks,errors" in open(str(job_log.job_log_path())).read()


def test_once_verified_delete_goes_out_with_no_body_and_no_content_type(tmp_env, live_mode):
    seen = []

    def handler(r):
        seen.append(r)
        return httpx.Response(200, json={"id": "w/1"})

    client = Instantly(api_key="k", transport=httpx.MockTransport(handler), sleep=lambda s: None)
    client.webhooks_delete("w1")
    r = seen[0]
    assert r.method == "DELETE" and r.url.raw_path == b"/api/v2/webhooks/w1"
    assert r.content == b"" and "content-type" not in r.headers


# =============================================== defect 8: resume_account
def test_resume_account_sends_no_body_and_url_encodes_the_email(tmp_env, live_mode):
    seen = []

    def handler(r):
        seen.append(r)
        return httpx.Response(200, json={"status": 1})

    client = Instantly(api_key="k", transport=httpx.MockTransport(handler), sleep=lambda s: None)
    client.resume_account("lorenzo+x@myadvero.com")
    r = seen[0]
    assert r.method == "POST"
    assert r.url.raw_path == b"/api/v2/accounts/lorenzo%2Bx%40myadvero.com/resume"
    assert r.content == b"" and "content-type" not in r.headers


# ============================================ defect 9: label value checks
class _Labels(object):
    def __init__(self, value_of):
        self.rows, self.requests, self.value_of = [], [], value_of

    def __call__(self, request):
        self.requests.append(request)
        if request.method == "GET":
            return httpx.Response(200, json={"items": self.rows, "next_starting_after": None})
        body = json.loads(request.content)
        row = dict(body, id="lab-%d" % len(self.rows))
        row.update(self.value_of(len(self.rows)))
        self.rows.append(row)
        return httpx.Response(200, json=row)


def _labels_run(tmp_path, value_of):
    server = _Labels(value_of)
    client = Instantly(api_key="k", transport=httpx.MockTransport(server), sleep=lambda s: None)
    values = tmp_path / "values.json"
    code = P0.main(["--labels", "--apply", "--yes"], client=client, now=NOW, out=lambda s: None,
                   backup_dir=str(tmp_path / "b"), label_values_path=str(values))
    return code, json.loads(values.read_text())


def test_label_values_record_their_source_key(tmp_env, live_mode, tmp_path):
    code, rec = _labels_run(tmp_path, lambda i: {"interest_value": 20000 + i})
    assert code == 0 and rec["complete"] is True
    assert set(m["value_key"] for m in rec["labels"].values()) == {"interest_value"}


def test_label_values_that_repeat_are_not_complete(tmp_env, live_mode, tmp_path):
    code, rec = _labels_run(tmp_path, lambda i: {"interest_status": 7})
    assert code == P0.EXIT_API and rec["complete"] is False
    assert any("not distinct" in p for p in rec["problems"])


def test_label_values_that_are_built_in_interest_codes_are_not_complete(tmp_env, live_mode, tmp_path):
    code, rec = _labels_run(tmp_path, lambda i: {"interest_status": [1, -1, 0, 2, 3, 4, -2, -3, -4, 101, 102][i]})
    assert code == P0.EXIT_API and rec["complete"] is False
    assert any("built-in interest code" in p for p in rec["problems"])


# ======================= defect 10: a create that raised but landed is recorded
def test_a_create_that_raised_but_landed_is_reconciled_into_the_ledger(tmp_env, live_mode, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("REPLY_ENGINE_BASE_URL", TARGET[: -len("/webhooks/instantly")])
    monkeypatch.setenv("REPLY_ENGINE_SECRET", "s3cr3t")
    state = {"live": [], "n": 0}
    reqs = []

    def handler(r):
        reqs.append(r)
        if r.method == "GET":
            return httpx.Response(200, json=state["live"])
        state["n"] += 1
        row = dict(json.loads(r.content), id="wh-%d" % state["n"])
        state["live"].append(row)                               # it lands...
        if state["n"] == 2:
            return httpx.Response(504, text="gateway timeout")  # ...but this one answers 504
        return httpx.Response(200, json=row)

    client = Instantly(api_key="k", transport=httpx.MockTransport(handler), sleep=lambda s: None)
    bdir = str(tmp_path / "backups")
    code = cw.main(["--apply", "--yes"], reader=lambda p: "apply", client=client, backup_dir=bdir)
    out = capsys.readouterr().out
    assert code == 3                                            # the error is still reported
    ids = sorted(e["id"] for e in cw.load_ledger(bdir))
    assert ids == sorted("wh-%d" % i for i in range(1, len(cw.EVENT_TYPES) + 1))
    assert "recording wh-2" in out
    assert [e for e in cw.load_ledger(bdir) if e["id"] == "wh-2"][0]["recorded_by"] == "reconcile"
    assert [r.method for r in reqs].count("POST") == len(cw.EVENT_TYPES)     # a write is never retried
    # a re-run creates nothing and records nothing new
    n = len(reqs)
    assert cw.main(["--apply", "--yes"], reader=lambda p: "apply", client=client, backup_dir=bdir) == 0
    assert [r.method for r in reqs[n:]] == ["GET"]


# ================================================================== round 3
# r2_p12: a restore acts only on a read taken AFTER its own confirmation
def test_r3_restore_refuses_when_live_moves_while_its_prompt_is_open(tmp_env, live_mode, tmp_path):
    fake = FakeInstantly()
    assert _cap(fake, ["--input", plan_file(tmp_path, limits={"cleaning_reactivation": 100}),
                       "--campaign", "cleaning_reactivation", "--apply", "--yes"], tmp_path)[0] == 0
    point = tmp_path / "backups" / ("capacity_%s_%s.json" % (CR, STAMP))
    files_before = _files(tmp_path)

    def confirm(_prompt):          # the burned a1 is removed in another terminal meanwhile
        fake.campaigns[CR]["email_list"] = [e for e in fake.campaigns[CR]["email_list"] if e != "a1@d1.com"]
        return "cleaning_reactivation"

    n = len(fake.requests)
    out = []
    code = cap.main(["--restore", str(point), "--campaign", "cleaning_reactivation"], client=fake.client(),
                    now=NOW + timedelta(days=1), out=out.append, backup_dir=str(tmp_path / "backups"),
                    confirm=confirm)
    assert code == cap.EXIT_REFUSED
    assert [r.method for r in fake.requests[n:]] == ["GET", "GET"]           # read, prompt, re-read; no PATCH
    assert _files(tmp_path) == files_before                                  # no .prerestore either
    assert "a1@d1.com" not in fake.campaigns[CR]["email_list"]
    text = "\n".join(out)
    assert "MOVED WHILE THE PROMPT WAS OPEN: email_list 5 -> 4 inboxes; removes a1@d1.com" in text
    rows = open(str(job_log.job_log_path())).read()
    assert "moved_during_prompt" in rows


def test_r3_prerestore_holds_the_state_read_after_the_prompt(tmp_env, live_mode, tmp_path):
    fake = FakeInstantly()
    assert _cap(fake, ["--input", plan_file(tmp_path, limits={"cleaning_reactivation": 100}),
                       "--campaign", "cleaning_reactivation", "--apply", "--yes"], tmp_path)[0] == 0
    point = tmp_path / "backups" / ("capacity_%s_%s.json" % (CR, STAMP))

    def confirm(_prompt):          # a field the point does not own moves: still safe
        fake.campaigns[CR]["pl_value"] = 4321
        return "cleaning_reactivation"

    code = cap.main(["--restore", str(point), "--campaign", "cleaning_reactivation"], client=fake.client(),
                    now=NOW + timedelta(days=1), out=lambda s: None, backup_dir=str(tmp_path / "backups"),
                    confirm=confirm)
    assert code == 0
    pre = [f for f in _files(tmp_path) if f.endswith(".prerestore.json")]
    assert len(pre) == 1
    assert json.loads((tmp_path / "backups" / pre[0]).read_text())["pl_value"] == 4321


# r2_p13: the after-image is what Instantly stored, so its own defaults are not drift
def test_r3_server_defaults_on_store_do_not_block_the_restore(tmp_env, live_mode, tmp_path):
    from changesets.tests import test_phase0 as T0
    with open(T0.SNAPSHOT) as fh:
        state = {c["id"]: c for c in json.load(fh)["items"]}
    original = copy.deepcopy(state[CR]["sequences"])
    reqs = []

    def handler(r):
        reqs.append(r)
        cid = r.url.path.rsplit("/", 1)[1]
        if r.method == "PATCH":
            body = json.loads(r.content)
            for seq in body.get("sequences") or []:
                for st in seq.get("steps") or []:
                    for v in st.get("variants") or []:
                        v.setdefault("v_disabled", False)          # the server fills a default
            state[cid].update(body)
        return httpx.Response(200, json=state[cid])

    client = Instantly(api_key="k", transport=httpx.MockTransport(handler), sleep=lambda s: None)
    bdir = tmp_path / "b"
    assert P0.main(["--apply", "--campaign", "cleaning_reactivation", "--yes", "--no-diff"], client=client,
                   now=NOW, out=lambda s: None, backup_dir=str(bdir)) == 0
    point = bdir / [f for f in os.listdir(str(bdir)) if f.endswith("Z.json")][0]
    meta = json.loads(point.read_text())["_rollback_point"]
    assert meta["after_source"] == "stored"
    assert meta["after"]["sequences"][0]["steps"][0]["variants"][0]["v_disabled"] is False
    out = []
    n = len(reqs)
    code = P0.main(["--apply", "--restore", str(point), "--campaign", "cleaning_reactivation"], client=client,
                   now=NOW + timedelta(minutes=30), out=out.append, backup_dir=str(bdir),
                   confirm=lambda p: "cleaning_reactivation")
    # it proceeds without the override: no drift refusal, and the before-image is sent
    assert not any("CHANGED SINCE THE APPLY" in l or "REFUSED" in l for l in out), out
    assert [r.method for r in reqs[n:]] == ["GET", "GET", "PATCH", "GET"]
    sent = json.loads(reqs[n + 2].content)
    assert sent["sequences"] == original and set(sent) <= set(meta["fields"])
    # This fake adds the default on EVERY store, restore included, so the
    # restored copy can never equal the before-image exactly. The restore does
    # not claim success; it names the path so the default is obvious.
    assert code == P0.EXIT_API
    assert any("differs at sequences[0].steps[0].variants[0].v_disabled: <absent> -> false" in l for l in out)


def test_r3_a_drift_line_on_a_nested_field_names_the_path(tmp_env, live_mode, tmp_path):
    seq = [{"steps": [{"type": "email", "delay": 3, "variants": [{"subject": "A", "body": "a"}]}]}]
    seq_after = copy.deepcopy(seq)
    seq_after[0]["steps"][0]["variants"][0]["body"] = "b"
    fake = FakeInstantly(campaigns={CR: {"id": CR, "name": "CR", "status": 1, "email_list": ["a1@d1.com"],
                                         "daily_limit": 50, "sequences": copy.deepcopy(seq_after)}})
    bdir = str(tmp_path / "backups")
    before = dict(fake.campaigns[CR], sequences=seq)
    point = R.write_point(bdir, "phase0_%s_x" % CR,
                          R.build_point("phase0", R.KIND_APPLY, before, ["sequences"], NOW, CR,
                                        "cleaning_reactivation", after={"sequences": seq_after}))
    fake.campaigns[CR]["sequences"][0]["steps"][0]["delay"] = 5         # hand edit after the apply
    out = []
    code, info = R.restore(fake.client(), "phase0", point, CR, "cleaning_reactivation", bdir,
                           "phase0_%s_y" % CR, NOW, out.append)
    assert code == R.EXIT_REFUSED
    assert any("differs from the after-image at sequences[0].steps[0].delay: 3 -> 5" in l for l in out)
    assert info["drift"] and "sequences[0].steps[0].delay" in info["drift"][0]


def test_r3_landed_after_error_records_the_stored_values(tmp_env, live_mode, tmp_path):
    fake = FakeInstantly(fail_patch={CR: (504, True)})
    code, _ = _cap(fake, ["--input", plan_file(tmp_path, limits={"cleaning_reactivation": 100}),
                          "--campaign", "cleaning_reactivation", "--apply", "--yes"], tmp_path)
    assert code == cap.EXIT_API
    meta = json.loads((tmp_path / "backups" / ("capacity_%s_%s.json" % (CR, STAMP))).read_text())["_rollback_point"]
    assert meta["outcome"] == "landed_after_error" and meta["after_source"] == "stored"
    assert meta["after"] == {"daily_limit": 100, "email_list": fake.campaigns[CR]["email_list"]}


# r2_p10: the override always needs a person at the prompt, and the Job_Log says so
@pytest.mark.parametrize("script", ["capacity", "promotion", "inbox_actions", "phase0"])
def test_r3_override_with_yes_is_refused_before_any_request(tmp_env, live_mode, tmp_path, script, capsys):
    fake = FakeInstantly()
    point = str(tmp_path / "whatever.json")
    common = ["--restore", point, "--campaign", "cleaning_reactivation", "--override-later-changes", "--yes"]
    out = []
    if script == "capacity":
        code = cap.main(common, client=fake.client(), now=NOW, out=out.append, backup_dir=str(tmp_path))
    elif script == "promotion":
        code = ap.main(common, client=fake.client(), now=NOW, backup_dir=str(tmp_path))
    elif script == "inbox_actions":
        code = A.main(common, client=fake.client(), out=out.append, now=NOW, directory=tmp_path)
    else:
        code = P0.main(["--apply"] + common, client=fake.client(), now=NOW, out=out.append,
                       backup_dir=str(tmp_path))
    text = "\n".join(out) + capsys.readouterr().err
    assert code == 2
    assert "--override-later-changes cannot be combined with --yes" in text
    assert fake.requests == []


def test_r3_the_job_log_row_records_the_override_and_the_drift(tmp_env, live_mode, tmp_path):
    fake, point = _capacity_then_burned_removal(tmp_path)
    prompts = []
    code = cap.main(["--restore", str(point), "--campaign", "cleaning_reactivation", "--override-later-changes"],
                    client=fake.client(), now=NOW + timedelta(days=3), out=lambda s: None,
                    backup_dir=str(tmp_path / "backups"),
                    confirm=lambda p: prompts.append(p) or "cleaning_reactivation")
    assert code == 0 and len(prompts) == 1
    import csv
    rows = list(csv.DictReader(open(str(job_log.job_log_path()))))
    row = [r for r in rows if r["status"] == "restored"][-1]
    details = json.loads(row["details"])
    assert details["override_later_changes"] is True
    assert details["drift"] and "CHANGED SINCE THE APPLY: email_list" in details["drift"][0]
    assert "removes a1@d1.com" in details["drift"][0]
