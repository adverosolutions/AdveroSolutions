import pytz
import pytest

from shared import job_log, settings


def test_default_mode_is_shadow(shadow_mode):
    assert settings.get_mode() == "shadow"
    assert settings.is_live() is False


def test_guard_write_shadow_returns_record_and_logs(tmp_env, shadow_mode):
    rec = settings.guard_write("instantly", "reply_to_email", {"reply_to_uuid": "abc"})
    assert rec["shadow"] is True
    assert rec["system"] == "instantly"
    assert rec["action"] == "reply_to_email"
    assert rec["payload"] == {"reply_to_uuid": "abc"}
    assert "ts" in rec
    rows = job_log.read_shadow_log()
    assert len(rows) == 1
    assert rows[0]["system"] == "instantly"
    assert rows[0]["action"] == "reply_to_email"
    assert rows[0]["payload"] == {"reply_to_uuid": "abc"}
    assert rows[0]["mode"] == "shadow"


def test_guard_write_live_requires_both_flags(tmp_env, monkeypatch):
    monkeypatch.setenv("MODE", "live")
    monkeypatch.delenv("ALLOW_LIVE_WRITES", raising=False)
    assert settings.is_live() is False
    rec = settings.guard_write("ghl", "upsert_contact", {"email": "a@b.co"})
    assert rec["shadow"] is True
    assert len(job_log.read_shadow_log()) == 1


def test_guard_write_live(tmp_env, live_mode):
    assert settings.is_live() is True
    rec = settings.guard_write("ghl", "upsert_contact", {"email": "a@b.co"})
    assert rec["shadow"] is False
    assert rec["system"] == "ghl"
    # live writes are not written to the shadow log
    assert job_log.read_shadow_log() == []


def test_guard_write_live_leaves_an_intent_row_before_the_call(tmp_env, live_mode):
    """Shadow leaves a row per intended write; live has to as well, or a write
    that dies at the gateway leaves nothing to reconcile against."""
    import csv

    settings.guard_write("instantly", "reply_to_email", {"reply_to_uuid": "u1", "to": "lead@x.com"})
    with open(job_log.job_log_path(), newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert [(r["job"], r["status"]) for r in rows] == [("instantly.reply_to_email", "live_write_intent")]
    assert "lead@x.com" in rows[0]["details"] and rows[0]["mode"] == "live"


def test_allow_flag_alone_is_not_live(monkeypatch):
    monkeypatch.setenv("MODE", "shadow")
    monkeypatch.setenv("ALLOW_LIVE_WRITES", "1")
    assert settings.is_live() is False


def test_require_live_raises_in_shadow(shadow_mode):
    with pytest.raises(settings.LiveWriteBlocked):
        settings.require_live("instantly", "pause_account")


def test_require_live_passes_when_live(live_mode):
    settings.require_live("instantly", "pause_account")


def test_constants_and_ids():
    assert settings.TZ.zone == "America/Chicago"
    assert settings.TZ == pytz.timezone("America/Chicago")
    assert settings.SEND_WINDOW == (7, 19)
    assert settings.SLOT_WINDOW == (12, 18)
    assert settings.MIN_LEAD_HOURS == 4
    assert settings.MAX_BUSINESS_DAYS == 5
    assert settings.CADENCE_HOUR == 10
    assert settings.IDS["ghl"]["location_id"] == "ebyNANPagaK7ycf1pfge"
    assert settings.GHL_LOCATION_ID == "ebyNANPagaK7ycf1pfge"
    assert settings.GHL_STAGES["new_reply"] == "f000f05d-5732-40c1-866a-bd71cd0f95b6"
    assert settings.GHL_CALENDAR_ID == "GDugwLmZNdsD13RBDnRu"
    assert len(settings.CAMPAIGNS) == 6
    assert settings.CAMPAIGN_BY_ID["f00c5e28-fdc4-4d84-a7e6-dfba9695f35d"]["key"] == "bookkeeping_reactivation"
    assert "20–30% of first-year fees" in settings.OFFERS_MD


def test_offers_md_is_loaded_and_carries_the_canonical_numbers():
    """Every price and guarantee a draft may quote comes from config/offers.md;
    an empty OFFERS_MD makes the reply engine reject every draft with a number."""
    assert settings.OFFERS_LOADED is True
    assert settings.OFFERS_MD.strip()
    for needle in ("20–30%", "$24,000", "$15,000", "$40,000", "$2,500–5,000/mo"):
        assert needle in settings.OFFERS_MD, needle
    assert settings.require_offers() is settings.OFFERS_MD


def test_missing_offers_file_fails_loudly(tmp_path, caplog):
    with caplog.at_level("ERROR"):
        text = settings.load_offers(tmp_path / "nope.md")
    assert text == ""
    assert settings.OFFERS_LOADED is False
    assert "offers.md could not be read" in caplog.text
    # restore the module state for the rest of the session
    settings.OFFERS_MD = settings.load_offers()
    assert settings.OFFERS_LOADED is True


# --------------------------------------------------------------------------
# Every environment key the deployed code reads must be deployable.
#
# Four capabilities the runbooks tell Lorenzo to switch on (Zoom's webhook
# secret, A2P, an ntfy token, the D6 hold) read environment variables that were
# in no Modal secret, so they could not be switched on in the container without
# editing modal_app.py. This walks the AST of everything under services/ and
# jobs/ and asserts that each key is either in SECRET_KEYS or explicitly listed
# as deliberately-not-deployed.
import ast
import os

from shared.paths import BASE_DIR


def _module_env_keys(path):
    """Every literal env key read in one module, resolving NAME = "KEY" consts."""
    with open(path, "r", encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=str(path))
    consts = {}
    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and isinstance(node.value, ast.Str)):
            consts[node.targets[0].id] = node.value.s
    found = set()
    for node in ast.walk(tree):
        arg = None
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.args:
            base = node.func.value
            is_environ = (isinstance(base, ast.Attribute) and base.attr == "environ"
                          and isinstance(base.value, ast.Name) and base.value.id == "os")
            is_os = isinstance(base, ast.Name) and base.id == "os"
            if (node.func.attr == "get" and is_environ) or (node.func.attr == "getenv" and is_os):
                arg = node.args[0]
        elif isinstance(node, ast.Subscript):
            base = node.value
            if (isinstance(base, ast.Attribute) and base.attr == "environ"
                    and isinstance(base.value, ast.Name) and base.value.id == "os"):
                arg = node.slice.value if isinstance(node.slice, ast.Index) else node.slice
        if arg is None:
            continue
        if isinstance(arg, ast.Str):
            found.add(arg.s)
        elif isinstance(arg, ast.Name) and arg.id in consts:
            found.add(consts[arg.id])
    return found


def _deployed_env_keys():
    out = {}
    for root_name in ("services", "jobs", "shared"):
        root = BASE_DIR / root_name
        for dirpath, dirnames, filenames in os.walk(str(root)):
            parts = dirpath.split(os.sep)
            if "tests" in parts or "__pycache__" in parts:
                continue
            for name in filenames:
                if not name.endswith(".py"):
                    continue
                path = os.path.join(dirpath, name)
                for key in _module_env_keys(path):
                    out.setdefault(key, []).append(os.path.relpath(path, str(BASE_DIR)))
    return out


def test_every_env_key_is_deployable():
    from services.reply_engine import modal_app

    keys = _deployed_env_keys()
    known = set(modal_app.SECRET_KEYS) | set(modal_app.ENV_NOT_IN_SECRET)
    missing = {k: v for k, v in keys.items() if k not in known}
    assert not missing, (
        "these environment keys are read by deployed code but are in neither "
        "modal_app.SECRET_KEYS nor ENV_NOT_IN_SECRET, so they cannot be set in the "
        "container: %s" % missing)


def test_the_four_capabilities_the_runbooks_switch_on_are_in_the_secret():
    """Zoom's webhook secret, A2P, the ntfy token and the D6 hold: each one is a
    step in a runbook, and each was impossible to perform on Modal."""
    from services.reply_engine import modal_app

    for key in ("ZOOM_WEBHOOK_SECRET", "A2P_10DLC_REGISTERED", "NTFY_TOKEN", "CADENCE_D6_HOLD", "BASE_URL"):
        assert key in modal_app.SECRET_KEYS, key


def test_the_deploy_runbook_lists_every_secret_key_it_tells_lorenzo_to_create():
    """A key in SECRET_KEYS that step 2a never mentions is a key that is never
    set: BASE_URL was in the list and absent from the command, so every Approve
    link during the 48-hour watch pointed at localhost."""
    from services.reply_engine import modal_app

    with open(str(BASE_DIR / "runbooks" / "deployment.md"), "r", encoding="utf-8") as fh:
        runbook = fh.read()
    step = runbook.split("# 2a.", 1)[1].split("# 2b.", 1)[0]
    optional = {"REPLY_ENGINE_BASE_URL", "GHL_PRIVATE_INTEGRATION_TOKEN", "SHOW_RATE_SENDER",
                "AUTO_SEND_AFTER_MINUTES", "LOOM_URL_GENERIC", "LOG_LEVEL", "ZOOM_URL_VALIDATION",
                "NTFY_ALLOW_SENSITIVE"}
    for key in modal_app.SECRET_KEYS:
        if key in optional:
            continue
        assert key in step, "%s is in SECRET_KEYS but runbooks/deployment.md step 2a never sets it" % key
