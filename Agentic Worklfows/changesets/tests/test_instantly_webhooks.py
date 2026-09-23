"""changesets/instantly_webhooks.py: the webhook change-set (deployment step 4/6).

Nothing here touches a live system: every Instantly call goes through an
httpx.MockTransport and MODE stays shadow unless a test opts into live_mode
with a mocked transport.
"""
import json
import os

import httpx
import pytest

from shared import job_log
from shared.instantly import Instantly, InstantlyError

from changesets import instantly_webhooks as cw

URL = "https://advero--advero-reply-engine-web.modal.run"
TARGET = URL + "/webhooks/instantly"


class Recorder(object):
    def __init__(self, handler=None):
        self.requests = []
        self.handler = handler

    def __call__(self, request):
        self.requests.append(request)
        if self.handler is not None:
            return self.handler(request)
        return httpx.Response(200, json={"ok": True})


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("REPLY_ENGINE_BASE_URL", URL)
    monkeypatch.setenv("REPLY_ENGINE_SECRET", "s3cr3t")
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    monkeypatch.setattr(cw, "BACKUP_DIR", str(tmp_path / "backups"))
    return tmp_path


def _client(handler=None):
    rec = Recorder(handler)
    return Instantly(api_key="k", transport=httpx.MockTransport(rec)), rec


def test_the_payload_uses_target_hook_url_and_carries_the_secret_header(env):
    """config/instantly_api_contract.md: target_hook_url is the only required
    property. deployment.md said target_url once, which creates a webhook with
    no target and silently delivers nothing."""
    desired = cw.desired_webhooks()
    assert len(desired) == len(cw.EVENT_TYPES)
    for row in desired:
        assert row["target_hook_url"] == TARGET
        assert "target_url" not in row
        assert row["headers"] == {"X-Advero-Secret": "s3cr3t"}
        assert row["name"].startswith("advero-reply-engine")
    assert [r["event_type"] for r in desired] == list(cw.EVENT_TYPES)


def test_no_base_url_and_no_secret_refuse_before_anything_is_read(monkeypatch, tmp_path):
    monkeypatch.delenv("REPLY_ENGINE_BASE_URL", raising=False)
    monkeypatch.delenv("BASE_URL", raising=False)
    monkeypatch.delenv("REPLY_ENGINE_SECRET", raising=False)
    with pytest.raises(ValueError) as exc:
        cw.target_url()
    assert "no base URL" in str(exc.value)
    monkeypatch.setenv("REPLY_ENGINE_BASE_URL", URL)
    with pytest.raises(ValueError) as exc:
        cw.secret()
    assert "REPLY_ENGINE_SECRET" in str(exc.value)
    # a non-http base is refused too: the API enforces ^https?://
    monkeypatch.setenv("REPLY_ENGINE_BASE_URL", "advero.modal.run")
    with pytest.raises(ValueError):
        cw.target_url()


def test_dry_run_reads_writes_a_dryrun_backup_and_creates_nothing(env, capsys):
    live = [{"id": "w1", "event_type": "reply_received", "target_hook_url": TARGET, "name": "advero-reply-engine reply_received"},
            {"id": "w9", "event_type": "email_sent", "target_hook_url": "https://someone.else/hook", "name": "Lorenzo's own"}]
    client, rec = _client(lambda r: httpx.Response(200, json=live))
    plan = cw.diff(cw.desired_webhooks(), cw.fetch_live(client))
    assert [r["event_type"] for r in plan["skip"]] == ["reply_received"]     # already there, left alone
    assert len(plan["create"]) == len(cw.EVENT_TYPES) - 1
    assert all(r.method == "GET" for r in rec.requests)                      # read-only

    path = cw.write_backup(plan["live"], dry_run=True)
    assert path.endswith(".dryrun.json")
    saved = json.load(open(path, "r", encoding="utf-8"))
    assert len(saved) == 2


def test_the_documented_dry_run_works_before_the_secret_exists(env, monkeypatch, capsys):
    """runbooks/deployment.md step 4 runs the dry-run with only
    REPLY_ENGINE_BASE_URL set: the secret is generated later, in step 2a.
    desired_webhooks() called secret() unconditionally, so the one command
    whose job is to prove this change-set is safe died with a raw ValueError
    traceback after writing a stray backup."""
    monkeypatch.delenv("REPLY_ENGINE_SECRET", raising=False)
    live = [{"id": "w1", "event_type": "reply_received", "target_hook_url": TARGET, "name": "advero-reply-engine reply_received"}]
    client, rec = _client(lambda r: httpx.Response(200, json=live))
    # Every job and change-set builds its client through
    # shared.instantly.default_client, so that is the one name a harness
    # has to replace to run the fleet offline.
    monkeypatch.setattr(cw, "default_client", lambda *a, **kw: client)

    assert cw.desired_webhooks(include_secret=False)[0]["headers"] == {"X-Advero-Secret": "<REPLY_ENGINE_SECRET>"}
    rc = cw.main(["--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "would create: %d" % (len(cw.EVENT_TYPES) - 1) in out
    assert "<redacted>" in out                     # the plan prints, with the header value masked
    assert "Traceback" not in out
    assert all(r.method == "GET" for r in rec.requests)
    # and the live path still refuses before any read when the secret is missing
    monkeypatch.setenv("MODE", "live")
    monkeypatch.setenv("ALLOW_LIVE_WRITES", "1")
    assert cw.main(["--apply", "--yes"]) == 1
    assert "REPLY_ENGINE_SECRET is unset" in capsys.readouterr().out


def test_the_backup_never_contains_the_secret(env):
    saved = cw.redact(cw.desired_webhooks()[0])
    assert saved["headers"] == {"X-Advero-Secret": "<redacted>"}
    assert "s3cr3t" not in json.dumps(saved)


def test_apply_and_rollback_refuse_in_shadow(env, capsys):
    assert cw.main(["--apply", "--yes"]) == 2
    assert "MODE=live" in capsys.readouterr().out
    assert cw.main(["--rollback", "--yes"]) == 2
    assert cw.main(["--apply", "--rollback", "--yes"]) == 2


def test_apply_without_yes_is_refused_even_in_live(env, live_mode, capsys):
    live = []
    client, rec = _client(lambda r: httpx.Response(200, json=live))
    assert cw.confirm("apply", 6, TARGET, assume_yes=False) is False
    # and the typed confirmation has to match
    assert cw.confirm("apply", 6, TARGET, assume_yes=True, reader=lambda _p: "y") is False
    assert cw.confirm("apply", 6, TARGET, assume_yes=True, reader=lambda _p: "apply") is True


def test_apply_in_shadow_records_would_do_and_makes_no_http(env, shadow_mode):
    client, rec = _client()
    plan = cw.diff(cw.desired_webhooks(), [])
    out = cw.apply(client, plan)
    assert rec.requests == []                               # guarded: nothing left the process
    assert len(out["created"]) == len(cw.EVENT_TYPES) and out["errors"] == []
    records = [r for r in job_log.read_shadow_log() if r["action"] == "webhooks_create"]
    assert len(records) == len(cw.EVENT_TYPES)
    assert records[0]["payload"]["target_hook_url"] == TARGET
    assert records[0]["payload"]["headers"] == {"X-Advero-Secret": "s3cr3t"}


def test_rollback_only_touches_recorded_ids_that_still_carry_our_name(env):
    """GOL-18: the docstring said URL AND name, the code did URL OR name. The
    rule is now: an id this change-set recorded at create time AND our prefix."""
    live = [{"id": "w1", "event_type": "reply_received", "target_hook_url": TARGET, "name": "advero-reply-engine reply_received"},
            {"id": "w2", "event_type": "email_sent", "target_hook_url": TARGET, "name": "Lorenzo's own, same URL"},
            {"id": "w3", "event_type": "lead_interested", "target_hook_url": "https://x/y", "name": "advero-reply-engine by hand"},
            {"id": "w9", "event_type": "email_sent", "target_hook_url": "https://someone.else/hook", "name": "Lorenzo's own"}]
    mine, theirs = cw.ours(live, ["w1", "w2"])
    assert [r["id"] for r in mine] == ["w1"]                  # w2 recorded but renamed: kept
    assert [r["id"] for r in theirs] == ["w2", "w3", "w9"]    # w3 named like ours, never recorded: kept
    assert cw.ours(live)[0] == []                             # no ledger, nothing is ours


def test_rollback_in_shadow_records_would_do_deletes(env, shadow_mode):
    client, rec = _client()
    mine = [{"id": "w1", "event_type": "reply_received", "target_hook_url": TARGET}]
    out = cw.rollback(client, mine)
    assert rec.requests == [] and out["errors"] == [] and len(out["deleted"]) == 1
    actions = [(r["system"], r["action"]) for r in job_log.read_shadow_log()]
    assert ("instantly", "webhooks_delete") in actions


def test_deployment_runbook_no_longer_calls_the_script_missing(env):
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    assert os.path.exists(os.path.join(root, "changesets", "instantly_webhooks.py"))
    with open(os.path.join(root, "runbooks", "deployment.md"), "r", encoding="utf-8") as fh:
        text = fh.read()
    assert "NOT BUILT YET" not in text
    assert "target_hook_url" in text and "target_url`, " not in text


# ------------------------------------------------------------- GOL-18 / item 5
def _server(live):
    """GET /webhooks, POST /webhooks (returns an id), DELETE /webhooks/{id}."""
    state = {"live": list(live), "n": 0}

    def handler(request):
        if request.method == "GET" and request.url.path == "/api/v2/webhooks":
            return httpx.Response(200, json=state["live"])
        if request.method == "POST" and request.url.path == "/api/v2/webhooks":
            state["n"] += 1
            row = dict(json.loads(request.content), id="new-%d" % state["n"])
            state["live"].append(row)
            return httpx.Response(200, json=row)
        if request.method == "DELETE" and request.url.path.startswith("/api/v2/webhooks/"):
            wid = request.url.path.rsplit("/", 1)[1]
            state["live"] = [r for r in state["live"] if r.get("id") != wid]
            return httpx.Response(200, json={"id": wid})
        return httpx.Response(404, text="unexpected")

    client, rec = _client(handler)
    return client, rec, state


def test_apply_records_the_created_ids_and_rollback_deletes_only_those(env, live_mode, monkeypatch, capsys):
    monkeypatch.setattr(cw, "DELETE_WEBHOOK_VERIFIED", True)     # as it will be after the rehearsal
    hand_made = {"id": "w9", "event_type": "email_sent", "target_hook_url": TARGET,
                 "name": "advero-reply-engine made by hand"}
    client, rec, state = _server([hand_made])
    bdir = str(env / "backups")
    assert cw.main(["--apply", "--yes"], reader=lambda _p: "apply", client=client, backup_dir=bdir) == 0
    posts = [r for r in rec.requests if r.method == "POST"]
    assert len(posts) == len(cw.EVENT_TYPES)
    body = json.loads(posts[0].content)
    assert posts[0].url.path == "/api/v2/webhooks"
    assert body == {"name": "advero-reply-engine reply_received", "event_type": "reply_received",
                    "target_hook_url": TARGET, "headers": {"X-Advero-Secret": "s3cr3t"}}
    ledger = cw.load_ledger(bdir)
    assert [e["id"] for e in ledger] == ["new-%d" % i for i in range(1, len(cw.EVENT_TYPES) + 1)]
    assert "s3cr3t" not in open(cw.ledger_path(bdir)).read()

    # rollback with NO secret and NO URL (the Modal app may be stopped)
    monkeypatch.delenv("REPLY_ENGINE_SECRET", raising=False)
    monkeypatch.delenv("REPLY_ENGINE_BASE_URL", raising=False)
    monkeypatch.delenv("BASE_URL", raising=False)
    n = len(rec.requests)
    capsys.readouterr()
    assert cw.main(["--rollback", "--yes"], reader=lambda _p: "rollback", client=client, backup_dir=bdir) == 0
    out = capsys.readouterr().out
    assert "NOT deleted" not in out                            # verified: every recorded id went
    deletes = [r for r in rec.requests[n:] if r.method == "DELETE"]
    assert sorted(r.url.path for r in deletes) == sorted("/api/v2/webhooks/%s" % e["id"] for e in ledger)
    assert all(r.content == b"" and "content-type" not in r.headers for r in deletes)
    assert [r["id"] for r in state["live"]] == ["w9"]          # the hand-made one survives
    assert rec.requests[-1].method == "GET"                     # success judged by a re-read
    assert all(e.get("deleted_at") for e in cw.load_ledger(bdir))
    # a second rollback deletes nothing
    n = len(rec.requests)
    assert cw.main(["--rollback", "--yes"], reader=lambda _p: "rollback", client=client, backup_dir=bdir) == 1
    assert rec.requests[n:] == []


def test_rollback_reports_a_delete_the_re_read_does_not_confirm(env, live_mode, monkeypatch):
    live = [{"id": "w1", "event_type": "reply_received", "target_hook_url": TARGET,
             "name": "advero-reply-engine reply_received"}]
    cw.save_ledger([{"id": "w1", "event_type": "reply_received"}], str(env / "backups"))
    monkeypatch.setattr(cw, "DELETE_WEBHOOK_VERIFIED", True)
    client, rec = _client(lambda r: httpx.Response(200, json=live if r.method == "GET" else {}))
    monkeypatch.delenv("REPLY_ENGINE_SECRET", raising=False)
    assert cw.main(["--rollback", "--yes"], reader=lambda _p: "rollback", client=client,
                   backup_dir=str(env / "backups")) == 3
    assert not cw.load_ledger(str(env / "backups"))[0].get("deleted_at")


def test_rollback_without_a_ledger_refuses_before_any_request(env, live_mode):
    client, rec = _client()
    assert cw.main(["--rollback", "--yes"], client=client, backup_dir=str(env / "backups")) == 1
    assert rec.requests == []


def test_rollback_in_shadow_is_refused_before_any_request(env):
    client, rec = _client()
    assert cw.main(["--rollback", "--yes"], client=client, backup_dir=str(env / "backups")) == 2
    assert rec.requests == []


def test_delete_is_marked_unverified_in_code():
    assert cw.DELETE_WEBHOOK_VERIFIED is False
    assert "UNVERIFIED" in cw.__doc__


def test_dry_run_combined_with_apply_or_rollback_is_refused(env, live_mode):
    client, rec = _client()
    assert cw.main(["--dry-run", "--apply", "--yes"], client=client) == 2
    assert cw.main(["--dry-run", "--rollback", "--yes"], client=client) == 2
    assert rec.requests == []


def test_dry_run_writes_neither_the_real_job_log_nor_changesets_backups(env, monkeypatch):
    """GOL-20 item 5 and SAF-10."""
    real = env / "production_job_log.csv"
    monkeypatch.setenv("JOB_LOG_PATH", str(real))
    live = [{"id": "w1", "event_type": "reply_received", "target_hook_url": TARGET, "name": "x"}]
    client, rec = _client(lambda r: httpx.Response(200, json=live))
    assert cw.main(["--dry-run"], client=client) == 0
    assert all(r.method == "GET" for r in rec.requests)
    assert not real.exists()
    assert os.environ["JOB_LOG_PATH"] == str(real)             # redirect undone
    assert not (env / "backups").exists()
    copies = os.listdir(str(env / "changeset_dryruns" / "webhooks"))
    assert len(copies) == 1 and copies[0].endswith(".dryrun.json")
