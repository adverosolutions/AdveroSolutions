"""Tests for changesets/inbox_actions/apply_inbox_actions.py.

Run: cd "Agentic Worklfows" && python3 -m pytest jobs/tests/test_deliverability_changeset.py -q

This is the only file in the deliverability set that can change live state, so
most of these tests are about the ways it must refuse.
"""
import json
import os
from datetime import datetime, timezone

import pytest

from shared import thresholds as TH
from shared.settings import LiveWriteBlocked
from changesets.inbox_actions import apply_inbox_actions as A
from jobs.tests.test_deliverability_monitor import StubClient, campaign, ct

NOW = ct("2026-09-22 09:00")
EMAILS = ["x@a.com", "y@a.com", "z@b.com"]


class ApplyClient(StubClient):
    def __init__(self, accounts_status=None, email_list=None, **kw):
        StubClient.__init__(self, campaigns={"c1": campaign("c1", "cid-1", email_list or EMAILS)}, **kw)
        self._status = accounts_status or {e: 1 for e in EMAILS}
        self.writes = []

    def _get(self, path, params=None):
        if path.startswith("accounts/"):
            email = path.split("/", 1)[1]
            if email not in self._status:
                raise KeyError(email)
            return {"email": email, "status": self._status[email], "warmup_status": 1,
                    "stat_warmup_score": 100}
        raise KeyError(path)

    def update_campaign(self, cid, payload):
        self.writes.append(("update_campaign", cid, payload))
        return {"id": cid, "email_list": payload["email_list"]}

    def pause_account(self, email):
        self.writes.append(("pause_account", email))
        return {"email": email, "status": 2}

    def resume_account(self, email):
        self.writes.append(("resume_account", email))
        return {"email": email, "status": 1}


def changeset(actions, pid="remove_from_email_list:x@a.com", status=None):
    p = {"id": pid, "kind": "remove_from_email_list", "target": "x@a.com", "severity": "high",
         "level": 3, "reason": "0.00% replies", "actions": actions, "evidence": {},
         "first_seen": "2026-09-22T12:00:00+00:00"}
    if status:
        p["status"] = status
    return {"generated_at": "2026-09-22T12:00:00+00:00", "proposals": [p]}


def patch_action(before=None, remove="x@a.com", add=None):
    return {"system": "instantly", "op": "patch_campaign_email_list", "campaign_key": "c1",
            "campaign_id": "cid-1", "remove": remove, "add": add,
            "expected_before": before if before is not None else list(EMAILS),
            "expected_after": [e for e in EMAILS if e != remove]}


# ----------------------------------------------------------------- the diff

def test_a_clean_patch_diffs_to_exactly_one_removal():
    client = ApplyClient()
    row = A.diff_action(client, patch_action())
    assert row["blocked"] is None
    assert set(row["before"]) - set(row["after"]) == {"x@a.com"}
    assert len(row["after"]) == 2


def test_a_patch_is_refused_when_live_no_longer_matches_what_the_proposal_saw():
    """PATCH email_list REPLACES the array. Applying a stale array silently
    re-adds an inbox someone removed this morning, or drops one just promoted."""
    client = ApplyClient(email_list=["x@a.com", "y@a.com"])       # z@b.com already gone
    row = A.diff_action(client, patch_action(before=list(EMAILS)))
    assert row["blocked"] and "no longer matches" in row["blocked"]
    assert "z@b.com" in row["blocked"]


def test_a_patch_that_would_empty_a_campaign_is_refused():
    client = ApplyClient(email_list=["x@a.com"])
    row = A.diff_action(client, patch_action(before=["x@a.com"]))
    assert row["blocked"] and "floor is %d" % A.MIN_EMAIL_LIST_AFTER_APPLY in row["blocked"]


def test_a_patch_that_changes_nothing_is_satisfied_not_blocked():
    """Already in the desired state is work somebody did, not half a change."""
    client = ApplyClient()
    row = A.diff_action(client, patch_action(remove="nobody@a.com"))
    assert row["blocked"] is None
    assert row["satisfied"] and "not in email_list" in row["satisfied"]


def test_pausing_an_already_paused_account_is_satisfied_not_blocked():
    client = ApplyClient(accounts_status={"x@a.com": 2, "y@a.com": 1, "z@b.com": 1})
    row = A.diff_action(client, {"op": "pause_account", "email": "x@a.com"})
    assert row["blocked"] is None
    assert row["satisfied"] and "already paused" in row["satisfied"]


def test_a_manual_action_is_marked_manual_not_blocked():
    for op in ("add_records", "create_placement_test", "canary_send", "stop_using_domain"):
        row = A.diff_action(ApplyClient(), {"op": op})
        assert row["applicable"] is False
        assert row["blocked"] is None
        assert "manual" in row["manual"]


def test_a_patch_that_leaves_a_campaign_thin_warns_but_does_not_block():
    client = ApplyClient(email_list=["x@a.com", "y@a.com"])
    row = A.diff_action(client, patch_action(before=["x@a.com", "y@a.com"]))
    assert row["blocked"] is None
    assert row["warning"] and "sends/day" in row["warning"]
    assert A.WARN_EMAIL_LIST_AFTER_APPLY > A.MIN_EMAIL_LIST_AFTER_APPLY


def test_an_unreadable_account_blocks_rather_than_assuming():
    client = ApplyClient()
    row = A.diff_action(client, {"op": "pause_account", "email": "ghost@a.com"})
    assert row["blocked"] and "could not read" in row["blocked"]


# ------------------------------------------------------------------- planning

def test_plan_skips_a_proposal_that_was_already_applied():
    rows = A.plan(ApplyClient(), changeset([patch_action()], status="applied"))
    assert rows[0]["skipped"] == "status is 'applied'"
    assert rows[0]["actions"] == []


def test_plan_filters_by_id():
    cs = changeset([patch_action()])
    assert A.plan(ApplyClient(), cs, only_id="nope") == []
    assert len(A.plan(ApplyClient(), cs, only_id="remove_from_email_list:x@a.com")) == 1


def test_print_plan_shows_the_actual_diff_lines():
    out = []
    A.print_plan(A.plan(ApplyClient(), changeset([patch_action(add="spare@i.com")])), out=out.append)
    text = "\n".join(out)
    assert "- x@a.com" in text and "+ spare@i.com" in text
    assert "0.00% replies" in text


# --------------------------------------------------------------------- applying

def test_apply_raises_in_shadow_mode():
    rows = A.plan(ApplyClient(), changeset([patch_action()]))
    with pytest.raises(LiveWriteBlocked):
        A.apply_rows(ApplyClient(), rows, NOW)


def test_apply_backs_the_campaign_up_before_patching_it(tmp_path, live_mode):
    client = ApplyClient()
    rows = A.plan(client, changeset([patch_action()]))
    results = A.apply_rows(client, rows, NOW, backup_dir=tmp_path)
    assert results[0]["backup"] and "campaign_cid-1_before_" in results[0]["backup"]
    saved = json.loads(open(results[0]["backup"]).read())
    assert saved["email_list"] == EMAILS          # the state BEFORE the patch
    assert client.writes[0][0] == "update_campaign"
    assert "x@a.com" not in client.writes[0][2]["email_list"]


def test_apply_records_a_failure_without_aborting_the_rest(tmp_path, live_mode):
    class Boom(ApplyClient):
        def update_campaign(self, cid, payload):
            raise RuntimeError("gateway 502")

    client = Boom()
    rows = A.plan(client, changeset([patch_action()]))
    results = A.apply_rows(client, rows, NOW, backup_dir=tmp_path)
    assert results[0]["error"] == "gateway 502"


# ------------------------------------------------------------------------ main

def test_main_defaults_to_a_dry_run_and_changes_nothing(tmp_path):
    path = tmp_path / "2026-09-22.json"
    path.write_text(json.dumps(changeset([patch_action()])))
    client = ApplyClient()
    out = []
    rc = A.main(["--dry-run", "--date", "2026-09-22"], client=client, out=out.append, now=NOW,
                directory=tmp_path)
    assert rc == A.EXIT_OK
    assert client.writes == []
    assert "nothing was changed" in "\n".join(out)


def test_main_refuses_apply_without_an_id(tmp_path):
    (tmp_path / "2026-09-22.json").write_text(json.dumps(changeset([patch_action()])))
    out = []
    rc = A.main(["--apply"], client=ApplyClient(), out=out.append, now=NOW,
                directory=tmp_path)
    assert rc == A.EXIT_REFUSED
    assert "one proposal at a time" in "\n".join(out)


def test_main_refuses_a_partial_apply_when_any_action_is_blocked(tmp_path, live_mode):
    cs = changeset([{"op": "pause_account", "email": "x@a.com"}, patch_action(before=["x@a.com"])],
                   pid="pause_inbox:x@a.com")
    (tmp_path / "2026-09-22.json").write_text(json.dumps(cs))
    client = ApplyClient()
    out = []
    rc = A.main(["--apply", "--id", "pause_inbox:x@a.com", "--yes"], client=client,
                out=out.append, now=NOW, directory=tmp_path)
    assert rc == A.EXIT_REFUSED
    assert client.writes == []
    assert "half-changed" in "\n".join(out)


def test_main_apply_requires_a_typed_confirmation(tmp_path, live_mode):
    (tmp_path / "2026-09-22.json").write_text(json.dumps(changeset([patch_action()])))
    client = ApplyClient()
    out = []
    rc = A.main(["--apply", "--id", "remove_from_email_list:x@a.com"], client=client,
                out=out.append, confirm=lambda prompt: "yes", now=NOW, directory=tmp_path)
    assert rc == A.EXIT_REFUSED and client.writes == []
    assert "confirmation did not match" in "\n".join(out)


def test_main_apply_marks_the_proposal_applied(tmp_path, monkeypatch, live_mode):
    monkeypatch.setattr(A, "BACKUP_DIR", tmp_path / "backups")
    path = tmp_path / "2026-09-22.json"
    path.write_text(json.dumps(changeset([patch_action()])))
    client = ApplyClient()
    out = []
    rc = A.main(["--apply", "--id", "remove_from_email_list:x@a.com"], client=client,
                out=out.append, confirm=lambda p: "remove_from_email_list:x@a.com", now=NOW,
                directory=tmp_path)
    assert rc == A.EXIT_OK
    assert client.writes and client.writes[0][0] == "update_campaign"
    after = json.loads(path.read_text())["proposals"][0]
    assert after["status"] == "applied" and after["applied_at"]


def test_changeset_path_ignores_the_level5_spec_and_the_sidecars(tmp_path):
    for name in ("level5_baseline_campaign.json", "last_placement.json", "last_canary.json"):
        (tmp_path / name).write_text("{}")
    assert A.changeset_path(directory=tmp_path) is None
    (tmp_path / "2026-09-22.json").write_text("{}")
    assert A.changeset_path(directory=tmp_path).name == "2026-09-22.json"


def test_a_patch_can_remove_several_addresses_at_once_for_a_domain_retirement():
    client = ApplyClient()
    action = {"system": "instantly", "op": "patch_campaign_email_list", "campaign_key": "c1",
              "campaign_id": "cid-1", "remove": ["x@a.com", "y@a.com"], "add": None,
              "expected_before": list(EMAILS), "expected_after": ["z@b.com"]}
    row = A.diff_action(client, action)
    assert row["blocked"] is None
    assert row["after"] == ["z@b.com"]


def test_a_multi_remove_that_empties_the_campaign_is_still_refused():
    client = ApplyClient()
    action = {"system": "instantly", "op": "patch_campaign_email_list", "campaign_key": "c1",
              "campaign_id": "cid-1", "remove": list(EMAILS), "add": None,
              "expected_before": list(EMAILS), "expected_after": []}
    row = A.diff_action(client, action)
    assert row["blocked"] and "floor is" in row["blocked"]


# ------------------------------------------- manual, satisfied and the backup

def retire_changeset(pid="retire_domain:a.com"):
    """What build_proposals now emits for a domain retirement: the email_list
    patches on their own proposal, and the registrar step on its own."""
    patch = {"system": "instantly", "op": "patch_campaign_email_list", "campaign_key": "c1",
             "campaign_id": "cid-1", "remove": ["x@a.com", "y@a.com"], "add": None,
             "expected_before": list(EMAILS), "expected_after": ["z@b.com"]}
    return {"generated_at": "2026-09-22T12:00:00+00:00", "proposals": [
        {"id": pid, "kind": "retire_domain", "target": "a.com", "severity": "high", "level": 3,
         "reason": "every inbox on a.com fails", "actions": [patch], "evidence": {}},
        {"id": "stop_using_domain:a.com", "kind": "stop_using_domain", "target": "a.com",
         "severity": "high", "level": 3, "reason": "stop buying from a.com",
         "actions": [{"system": "manual", "op": "stop_using_domain", "domain": "a.com"}],
         "evidence": {}},
    ]}


def test_retire_domain_applies_its_patches_and_reports_the_registrar_work_separately(
        tmp_path, monkeypatch, live_mode):
    """Domain retirement is the most consequential level 3 verdict and it used
    to be permanently unapplyable: the bundled manual `stop_using_domain` action
    was marked blocked, and the refuse-a-partial-apply rule then refused the
    real PATCH actions with it."""
    monkeypatch.setattr(A, "BACKUP_DIR", tmp_path / "backups")
    path = tmp_path / "2026-09-22.json"
    path.write_text(json.dumps(retire_changeset()))
    client = ApplyClient()
    out = []
    rc = A.main(["--apply", "--id", "retire_domain:a.com", "--yes"], client=client,
                out=out.append, now=NOW, directory=tmp_path)
    assert rc == A.EXIT_OK
    assert client.writes and client.writes[0][0] == "update_campaign"
    assert client.writes[0][2]["email_list"] == ["z@b.com"]
    assert json.loads(path.read_text())["proposals"][0]["status"] == "applied"


def test_the_registrar_step_is_its_own_proposal_and_executes_nothing(tmp_path, live_mode):
    (tmp_path / "2026-09-22.json").write_text(json.dumps(retire_changeset()))
    client = ApplyClient()
    out = []
    rc = A.main(["--apply", "--id", "stop_using_domain:a.com", "--yes"], client=client,
                out=out.append, now=NOW, directory=tmp_path)
    assert rc == A.EXIT_OK and client.writes == []
    assert "manual follow-up work" in "\n".join(out)


def test_a_proposal_whose_pause_already_happened_still_patches_the_email_list(
        tmp_path, monkeypatch, live_mode):
    """The likeliest human response to a critical card is to pause the inbox in
    the Instantly UI. That used to block the whole proposal, so the inbox stayed
    in every campaign's email_list and the monitor regenerated the same dead
    proposal every morning."""
    monkeypatch.setattr(A, "BACKUP_DIR", tmp_path / "backups")
    cs = changeset([{"system": "instantly", "op": "pause_account", "email": "x@a.com"},
                    patch_action()], pid="pause_inbox:x@a.com")
    path = tmp_path / "2026-09-22.json"
    path.write_text(json.dumps(cs))
    client = ApplyClient(accounts_status={"x@a.com": 2, "y@a.com": 1, "z@b.com": 1})
    out = []
    rc = A.main(["--apply", "--id", "pause_inbox:x@a.com", "--yes"], client=client,
                out=out.append, now=NOW, directory=tmp_path)
    assert rc == A.EXIT_OK
    assert [w[0] for w in client.writes] == ["update_campaign"]
    assert "x@a.com" not in client.writes[0][2]["email_list"]
    assert "already in the desired state" in "\n".join(out)


def test_apply_refuses_to_write_when_the_backup_cannot_be_saved(tmp_path, monkeypatch, live_mode):
    """CLAUDE.md: a live apply backs up the current object first. The backup
    used to return None on an unwritable directory and the PATCH went out
    anyway, with record['backup'] holding the string 'None'."""
    monkeypatch.setattr(A, "_backup", lambda *a, **k: None)
    client = ApplyClient()
    rows = A.plan(client, changeset([patch_action()]))
    results = A.apply_rows(client, rows, NOW, backup_dir=tmp_path)
    assert client.writes == []
    assert "REFUSED" in results[0]["error"] and "backup" in results[0]["error"]
    assert "backup" not in [k for k in results[0] if k == "backup" and results[0][k]]


def test_an_apply_dry_run_does_not_touch_the_production_job_log(tmp_path, monkeypatch):
    """The 48-hour shadow watch reads .tmp/job_log.csv and that file was
    quarantined once already for exactly this kind of pollution."""
    monkeypatch.setenv("JOB_LOG_PATH", str(tmp_path / "production_job_log.csv"))
    (tmp_path / "2026-09-22.json").write_text(json.dumps(changeset([patch_action()])))
    A.main(["--dry-run", "--date", "2026-09-22"], client=ApplyClient(), out=lambda s: None,
           now=NOW, directory=tmp_path)
    assert not (tmp_path / "production_job_log.csv").exists()
    # ... and the redirection is undone, so the next caller logs where it meant to.
    assert os.environ["JOB_LOG_PATH"] == str(tmp_path / "production_job_log.csv")


def test_both_email_list_floors_come_from_shared_thresholds():
    assert A.MIN_EMAIL_LIST_AFTER_APPLY is TH.MIN_EMAIL_LIST_AFTER_APPLY
    assert A.WARN_EMAIL_LIST_AFTER_APPLY is TH.WARN_EMAIL_LIST_AFTER_APPLY
