import os

import httpx
import pytest

from shared import notify as notify_mod
from shared.notify import format_actions, notify


@pytest.fixture(autouse=True)
def _reset(tmp_env, monkeypatch):
    notify_mod.reset_for_tests()
    monkeypatch.delenv("NOTIFY_EMAIL", raising=False)
    monkeypatch.delenv("NOTIFICATION_EMAIL", raising=False)
    monkeypatch.delenv("GMAIL_SENDER_EMAIL", raising=False)
    monkeypatch.delenv("GMAIL_APP_PASSWORD", raising=False)
    monkeypatch.delenv("NTFY_TOKEN", raising=False)
    monkeypatch.delenv("NTFY_ALLOW_SENSITIVE", raising=False)
    # The suite runs in MODE=shadow; the delivery tests below are about the
    # request shape, so they opt in explicitly (every transport is mocked).
    monkeypatch.setenv("NOTIFY_SHADOW_SEND", "1")
    yield
    notify_mod.reset_for_tests()


@pytest.fixture
def protected_topic(monkeypatch):
    """An authenticated ntfy topic: full detail and action buttons allowed."""
    monkeypatch.setenv("NTFY_TOKEN", "tk_secret")


def test_notify_off_records_instead_of_sending(monkeypatch):
    monkeypatch.setenv("NOTIFY", "off")
    res = notify("Positive reply", "Tiffany asked about pricing", priority="high",
                 actions=[("Approve", "https://a/approve"), ("Veto", "https://a/veto")], tags=["moneybag"],
                 click="https://app.instantly.ai/unibox")
    assert res == {"sent": False, "test": True, "record": notify_mod.sent_in_test[0]}
    rec = notify_mod.sent_in_test[0]
    assert rec["title"] == "Positive reply"
    assert rec["priority"] == "high"
    assert rec["actions"] == "view, Approve, https://a/approve; view, Veto, https://a/veto"
    assert rec["tags"] == ["moneybag"] and rec["click"] == "https://app.instantly.ai/unibox"


def test_format_actions_variants():
    assert format_actions(None) is None
    assert format_actions("view, X, https://x") == "view, X, https://x"
    assert format_actions([{"label": "Approve, now", "url": "https://a", "clear": True}]) == "view, Approve  now, https://a, clear=true"
    assert format_actions([("Veto", "https://v")]) == "view, Veto, https://v"


def test_ntfy_request_shape_with_env_topic(monkeypatch, protected_topic):
    monkeypatch.setenv("NOTIFY", "on")
    monkeypatch.setenv("NTFY_TOPIC", "lz-test-topic")
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"id": "m1"})

    res = notify("Draft ready", "Approve within 30 min", priority="urgent",
                 actions=[("Approve", "https://a/1"), ("Veto", "https://a/2")], tags=["warning"], click="https://c",
                 transport=httpx.MockTransport(handler))
    assert res["sent"] is True and res["topic"] == "lz-test-topic" and res["ntfy"]["status"] == 200
    req = seen[0]
    assert req.method == "POST" and str(req.url) == "https://ntfy.sh/lz-test-topic"
    assert req.headers["Title"] == "Draft ready"
    assert req.headers["Priority"] == "urgent"
    assert req.headers["Tags"] == "warning"
    assert req.headers["Click"] == "https://c"
    assert req.headers["Actions"] == "view, Approve, https://a/1; view, Veto, https://a/2"
    assert req.headers["Authorization"] == "Bearer tk_secret"
    assert req.content.decode("utf-8") == "Approve within 30 min"  # env topic: no subscribe banner
    assert notify_mod.sent_in_test == []


# --------------------------------------------------- shadow is a write gate
def test_notify_in_shadow_records_the_intent_and_sends_nothing(tmp_env, monkeypatch, shadow_mode):
    """MODE=shadow must not perform a real ntfy POST or a real Gmail send."""
    from shared import job_log

    monkeypatch.setenv("NOTIFY", "on")
    monkeypatch.delenv("NOTIFY_SHADOW_SEND", raising=False)
    monkeypatch.setenv("NTFY_TOPIC", "lz-test-topic")
    monkeypatch.setenv("NOTIFY_EMAIL", "adveroadvertising@gmail.com")
    monkeypatch.setenv("GMAIL_SENDER_EMAIL", "sender@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "app-pass")

    def boom(*a, **k):
        raise AssertionError("shadow mode must not open an SMTP connection")

    monkeypatch.setattr(notify_mod, "_smtp_factory", boom)
    seen = []
    res = notify("Positive reply from Tiffany", "tiffany@flowerhillfs.com asked about pricing",
                 transport=httpx.MockTransport(lambda r: seen.append(r) or httpx.Response(200)))
    assert res["sent"] is False and res["shadow"] is True and res["email"] is False
    assert seen == [], "no ntfy POST in shadow"
    rows = [r for r in job_log.read_shadow_log() if r["system"] == "notify"]
    assert rows and rows[-1]["action"] == "push_email"
    assert rows[-1]["payload"]["title"] == "Positive reply from Tiffany"


def test_notify_shadow_send_opt_in_delivers(tmp_env, monkeypatch, shadow_mode):
    monkeypatch.setenv("NOTIFY", "on")
    monkeypatch.setenv("NOTIFY_SHADOW_SEND", "1")
    monkeypatch.setenv("NTFY_TOPIC", "lz-test-topic")
    seen = []
    res = notify("x", "y", transport=httpx.MockTransport(lambda r: seen.append(r) or httpx.Response(200)))
    assert res["sent"] is True and len(seen) == 1


# ------------------------------------------- public topics carry no secrets
def test_public_topic_gets_no_lead_pii_no_links_and_no_action_buttons(monkeypatch):
    """ntfy.sh topics are world-readable and world-writable by anyone who knows
    the name: an Approve URL in the body is a one-tap live send for a stranger."""
    monkeypatch.setenv("NOTIFY", "on")
    monkeypatch.setenv("NTFY_TOPIC", "lz-law-guessable-topic")
    seen = []
    approve = "https://engine.example.com/approve/abc123.9f8e7d6c5b4a"
    notify("Positive reply from Tiffany",
           "tiffany@flowerhillfs.com asked about pricing.\nApprove: " + approve,
           actions=[("Approve", approve), ("Veto", approve + "/veto")], click=approve,
           transport=httpx.MockTransport(lambda r: seen.append(r) or httpx.Response(200)))
    req = seen[0]
    body = req.content.decode("utf-8")
    assert "tiffany@flowerhillfs.com" not in body and "[email hidden]" in body
    assert "abc123.9f8e7d6c5b4a" not in body and "https://" not in body
    assert "Actions" not in req.headers and "Click" not in req.headers
    assert "Tiffany" in req.headers["Title"]  # still useful as a ping
    assert "details in the email" in body


def test_protected_topic_keeps_the_full_card(monkeypatch, protected_topic):
    monkeypatch.setenv("NOTIFY", "on")
    monkeypatch.setenv("NTFY_TOPIC", "lz-test-topic")
    seen = []
    notify("Positive reply", "tiffany@flowerhillfs.com asked about pricing",
           actions=[("Approve", "https://a/1")],
           transport=httpx.MockTransport(lambda r: seen.append(r) or httpx.Response(200)))
    body = seen[0].content.decode("utf-8")
    assert "tiffany@flowerhillfs.com" in body
    assert seen[0].headers["Actions"] == "view, Approve, https://a/1"


def test_email_leg_keeps_the_full_detail_even_on_a_public_topic(monkeypatch):
    monkeypatch.setenv("NOTIFY", "on")
    monkeypatch.setenv("NTFY_TOPIC", "lz-public")
    monkeypatch.setenv("NOTIFY_EMAIL", "adveroadvertising@gmail.com")
    monkeypatch.setenv("GMAIL_SENDER_EMAIL", "sender@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "app-pass")
    calls = {}

    class FakeSMTP(object):
        def __init__(self, host, port, timeout=None):
            pass

        def login(self, user, pwd):
            pass

        def sendmail(self, frm, to, msg):
            calls["msg"] = msg

        def quit(self):
            pass

    monkeypatch.setattr(notify_mod, "_smtp_factory", FakeSMTP)
    notify("Positive reply", "tiffany@flowerhillfs.com asked about pricing",
           click="https://engine.example.com/approve/abc123.9f8e",
           transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    import email as email_mod

    body = email_mod.message_from_string(calls["msg"]).get_payload(decode=True).decode("utf-8")
    assert "tiffany@flowerhillfs.com" in body
    assert "abc123.9f8e" in body


def test_redact_helper():
    assert notify_mod.redact("mail tiffany@flowerhillfs.com now") == "mail [email hidden] now"
    assert notify_mod.redact("go to https://x.io/a?b=1 now") == "go to [link hidden] now"
    assert notify_mod.redact("nothing to hide") == "nothing to hide"


def test_generated_topic_is_persisted_and_announced_once(tmp_env, monkeypatch):
    monkeypatch.setenv("NOTIFY", "on")
    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    bodies = []

    def handler(request):
        bodies.append((str(request.url), request.content.decode("utf-8")))
        return httpx.Response(200, json={})

    transport = httpx.MockTransport(handler)
    res1 = notify("First", "hello", transport=transport)
    topic = res1["topic"]
    assert topic.startswith("advero-") and len(topic) == len("advero-") + 12
    assert (tmp_env / "ntfy_topic.txt").read_text().strip() == topic
    assert bodies[0][0] == "https://ntfy.sh/" + topic
    assert "https://ntfy.sh/" + topic in bodies[0][1]  # subscribe URL in the first message
    notify("Second", "again", transport=transport)
    assert bodies[1][1] == "again"
    # a fresh process re-reads the persisted topic
    notify_mod._state["topic"] = None
    assert notify_mod.get_topic() == topic


def test_non_ascii_title_is_rfc2047_encoded(monkeypatch):
    monkeypatch.setenv("NOTIFY", "on")
    monkeypatch.setenv("NTFY_TOPIC", "t")
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200)

    notify("Réponse positive", "ok", transport=httpx.MockTransport(handler))
    assert seen[0].headers["Title"].startswith("=?utf-8?")


def test_never_raises_on_transport_failure(monkeypatch):
    monkeypatch.setenv("NOTIFY", "on")
    monkeypatch.setenv("NTFY_TOPIC", "t")

    def handler(request):
        raise httpx.ConnectError("offline")

    res = notify("x", "y", transport=httpx.MockTransport(handler))
    assert res["sent"] is False and res["errors"] and "ntfy" in res["errors"][0]


def test_bad_status_is_reported_not_raised(monkeypatch):
    monkeypatch.setenv("NOTIFY", "on")
    monkeypatch.setenv("NTFY_TOPIC", "t")
    res = notify("x", "y", transport=httpx.MockTransport(lambda r: httpx.Response(500, text="boom")))
    assert res["sent"] is False and res["ntfy"]["ok"] is False


def test_email_sent_when_configured(monkeypatch):
    monkeypatch.setenv("NOTIFY", "on")
    monkeypatch.setenv("NTFY_TOPIC", "t")
    monkeypatch.setenv("NOTIFY_EMAIL", "adveroadvertising@gmail.com")
    monkeypatch.setenv("GMAIL_SENDER_EMAIL", "sender@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "app-pass")
    calls = {}

    class FakeSMTP(object):
        def __init__(self, host, port, timeout=None):
            calls["conn"] = (host, port)

        def login(self, user, pwd):
            calls["login"] = (user, pwd)

        def sendmail(self, frm, to, msg):
            calls["mail"] = (frm, to, msg)

        def quit(self):
            calls["quit"] = True

    monkeypatch.setattr(notify_mod, "_smtp_factory", FakeSMTP)
    res = notify("Subject line", "Body text", click="https://c", transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    assert res["email"] is True and res["sent"] is True
    assert calls["conn"] == ("smtp.gmail.com", 465)
    assert calls["login"] == ("sender@gmail.com", "app-pass")
    assert calls["mail"][0] == "sender@gmail.com" and calls["mail"][1] == ["adveroadvertising@gmail.com"]
    assert "Subject: Subject line" in calls["mail"][2]


def test_email_failure_never_raises(monkeypatch):
    monkeypatch.setenv("NOTIFY", "on")
    monkeypatch.setenv("NTFY_TOPIC", "t")
    monkeypatch.setenv("NOTIFY_EMAIL", "a@b.co")
    monkeypatch.setenv("GMAIL_SENDER_EMAIL", "s@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "p")

    def boom(*a, **k):
        raise RuntimeError("smtp down")

    monkeypatch.setattr(notify_mod, "_smtp_factory", boom)
    res = notify("x", "y", transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    assert res["sent"] is True and res["email"] is False
    assert any("email" in e for e in res["errors"])


# ------------------------------------------- the suite may never open a socket
def test_conftest_blocks_every_real_smtp_connection():
    """Regression guard for the 2026-09-22 finding: a full pytest run opened an
    authenticated session with smtp.gmail.com and sent a real message, because
    tests that turn NOTIFY on patched only the ntfy leg while
    shared.settings.load_env() had put the real Gmail credentials in the
    environment. load_env() now reads nothing under pytest, conftest.py
    scrubs the environment to an allowlist, and it replaces the _smtp_factory
    seam; this test fails if any of those locks is removed."""
    import smtplib

    import conftest

    assert notify_mod._smtp_factory is not smtplib.SMTP_SSL
    assert notify_mod._smtp_factory is conftest._refuse_smtp
    with pytest.raises(AssertionError):
        notify_mod._smtp_factory("smtp.gmail.com", 465, timeout=20)
    conftest.smtp_attempts.pop()  # this test's own deliberate attempt

    # and the credentials never arrive, so _email_config() short-circuits
    # first. leaked_after_import is what importing shared (and so load_env())
    # put back into the process AFTER conftest's scrub: with the real .env
    # files on disk it has to be empty.
    assert conftest.leaked_after_import == []
    for key in ("NOTIFICATION_EMAIL", "GMAIL_SENDER_EMAIL", "GMAIL_APP_PASSWORD"):
        assert not conftest.env_key_allowed(key), key
    assert notify_mod._email_config() is None


# ----------------------------------------- the ntfy token never leaves the wire
FAKE_NTFY_TOKEN = "tk_FAKE_bearer_0123456789"


def _files_under(root):
    for dirpath, _dirs, names in os.walk(str(root)):
        for name in names:
            path = os.path.join(dirpath, name)
            with open(path, "rb") as fh:
                yield path, fh.read()


def _assert_no_token_anywhere(result, root, caplog):
    import json

    from shared.store import JsonFileStore

    assert FAKE_NTFY_TOKEN not in repr(result)
    assert "Authorization" not in repr(result) and "Bearer" not in repr(result)
    # What a caller stores: approval.py saves the notify result in the store.
    stored = JsonFileStore(root / "caller_store.json")
    stored.set("approval:x", {"notify_result": result})
    assert FAKE_NTFY_TOKEN not in json.dumps(stored.get("approval:x"), default=str)
    for path, data in _files_under(root):   # store, shadow log, job log, topic file
        assert FAKE_NTFY_TOKEN.encode("utf-8") not in data, path
    assert FAKE_NTFY_TOKEN not in caplog.text


def test_the_ntfy_token_is_sent_but_never_reported_or_stored(tmp_env, monkeypatch, caplog):
    """SAF-5: the result used to carry the request headers, Authorization
    included, and approval.py saves that result into the JSON store."""
    from shared import job_log

    monkeypatch.setenv("NOTIFY", "on")
    monkeypatch.setenv("NTFY_TOPIC", "lz-test-topic")
    monkeypatch.setenv("NTFY_TOKEN", FAKE_NTFY_TOKEN)
    seen = []
    with caplog.at_level("DEBUG"):
        res = notify("Draft ready", "Approve within 30 min", actions=[("Approve", "https://a/1")],
                     transport=httpx.MockTransport(lambda r: seen.append(r) or httpx.Response(200)))
    # the token did authenticate the push, so the checks below are not vacuous
    assert seen[0].headers["Authorization"] == "Bearer " + FAKE_NTFY_TOKEN
    assert res["sent"] is True and res["ntfy"]["authenticated"] is True
    assert res["ntfy"]["headers"]["Actions"] == "view, Approve, https://a/1"
    assert job_log.read_shadow_log(), "the shadow row was written, and is checked below"
    _assert_no_token_anywhere(res, tmp_env, caplog)


def test_the_ntfy_token_is_not_stored_in_shadow_or_live(tmp_env, monkeypatch, caplog):
    monkeypatch.setenv("NOTIFY", "on")
    monkeypatch.setenv("NTFY_TOPIC", "lz-test-topic")
    monkeypatch.setenv("NTFY_TOKEN", FAKE_NTFY_TOKEN)
    monkeypatch.delenv("NOTIFY_SHADOW_SEND", raising=False)
    with caplog.at_level("DEBUG"):
        shadow = notify("x", "y", transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    assert shadow["shadow"] is True
    _assert_no_token_anywhere(shadow, tmp_env, caplog)

    monkeypatch.setenv("MODE", "live")
    monkeypatch.setenv("ALLOW_LIVE_WRITES", "1")
    with caplog.at_level("DEBUG"):
        live = notify("x", "y", transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    assert live["sent"] is True and live["shadow"] is False
    _assert_no_token_anywhere(live, tmp_env, caplog)


def test_an_error_that_quotes_the_token_is_scrubbed(tmp_env, monkeypatch, caplog):
    """An exception or an error body can echo the request back. Neither the
    errors list nor the log line may carry the token."""
    monkeypatch.setenv("NOTIFY", "on")
    monkeypatch.setenv("NTFY_TOPIC", "lz-test-topic")
    monkeypatch.setenv("NTFY_TOKEN", FAKE_NTFY_TOKEN)

    def boom(request):
        raise httpx.ConnectError("refused; sent %s" % request.headers["Authorization"], request=request)

    with caplog.at_level("DEBUG"):
        res = notify("x", "y", transport=httpx.MockTransport(boom))
    assert res["sent"] is False and res["errors"] and "[ntfy token hidden]" in res["errors"][0]
    _assert_no_token_anywhere(res, tmp_env, caplog)

    echo = httpx.MockTransport(lambda r: httpx.Response(401, text="bad token " + FAKE_NTFY_TOKEN))
    with caplog.at_level("DEBUG"):
        res = notify("x", "y", transport=echo)
    assert res["ntfy"]["status"] == 401 and "ntfy returned 401" in caplog.text
    _assert_no_token_anywhere(res, tmp_env, caplog)


def test_a_token_across_the_200_character_log_cut_is_still_masked(tmp_env, monkeypatch, caplog):
    """The error body used to be cut to 200 characters BEFORE masking, so a
    token straddling the cut left its first half in the log."""
    monkeypatch.setenv("NOTIFY", "on")
    monkeypatch.setenv("NTFY_TOPIC", "lz-test-topic")
    monkeypatch.setenv("NTFY_TOKEN", FAKE_NTFY_TOKEN)
    body = "x" * 190 + FAKE_NTFY_TOKEN + " trailing"
    assert body.index(FAKE_NTFY_TOKEN) < 200 < body.index(FAKE_NTFY_TOKEN) + len(FAKE_NTFY_TOKEN)
    echo = httpx.MockTransport(lambda r: httpx.Response(500, text=body))
    with caplog.at_level("DEBUG"):
        res = notify("x", "y", transport=echo)
    assert res["ntfy"]["status"] == 500 and "ntfy returned 500" in caplog.text
    for n in range(6, len(FAKE_NTFY_TOKEN) + 1):
        assert FAKE_NTFY_TOKEN[:n] not in caplog.text, "a %d-character prefix of the token was logged" % n
    _assert_no_token_anywhere(res, tmp_env, caplog)
