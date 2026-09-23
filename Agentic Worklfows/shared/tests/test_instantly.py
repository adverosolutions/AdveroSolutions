import json

import httpx
import pytest

from shared import job_log
from shared.instantly import Instantly, InstantlyError


class Recorder(object):
    """httpx.MockTransport handler that records every request."""

    def __init__(self, responses=None):
        self.requests = []
        self.responses = list(responses or [])

    def __call__(self, request):
        self.requests.append(request)
        if self.responses:
            item = self.responses.pop(0)
            if isinstance(item, httpx.Response):
                return item
            status, body = item
            return httpx.Response(status, json=body)
        return httpx.Response(200, json={"items": [], "next_starting_after": None})


def make(responses=None, **kw):
    rec = Recorder(responses)
    client = Instantly(api_key="test-key", transport=httpx.MockTransport(rec), sleep=lambda s: None, **kw)
    return client, rec


def body_of(request):
    return json.loads(request.content.decode("utf-8"))


# ------------------------------------------------------------------ reads
def test_list_campaigns_request_shape():
    client, rec = make([(200, {"items": [{"id": "c1"}], "next_starting_after": None})])
    out = client.list_campaigns()
    assert out["items"][0]["id"] == "c1"
    req = rec.requests[0]
    assert req.method == "GET"
    assert req.url.scheme == "https" and req.url.host == "api.instantly.ai"
    assert req.url.path == "/api/v2/campaigns"
    assert req.url.params["limit"] == "100"
    assert req.headers["Authorization"] == "Bearer test-key"
    assert req.headers["Content-Type"] == "application/json"


def test_get_campaign_and_email_and_lead_paths():
    client, rec = make([(200, {"id": "c1"}), (200, {"id": "e1"}), (200, {"id": "l1"})])
    client.get_campaign("c1")
    client.get_email("e1")
    client.get_lead("l1")
    assert [r.url.path for r in rec.requests] == ["/api/v2/campaigns/c1", "/api/v2/emails/e1", "/api/v2/leads/l1"]
    assert all(r.method == "GET" for r in rec.requests)


def test_list_emails_params():
    client, rec = make()
    client.list_emails(email_type="received", campaign_id="camp", limit=50, eaccount="lorenzo@myadvero.com")
    req = rec.requests[0]
    assert req.url.path == "/api/v2/emails"
    assert req.url.params["email_type"] == "received"
    assert req.url.params["campaign_id"] == "camp"
    assert req.url.params["limit"] == "50"
    assert req.url.params["eaccount"] == "lorenzo@myadvero.com"
    assert "starting_after" not in req.url.params


def test_list_leads_is_post_with_body():
    client, rec = make([(200, {"items": []})])
    client.list_leads(filter="FILTER_VAL_INTERESTED", campaign="camp", limit=25, contacts=["a@b.co"])
    req = rec.requests[0]
    assert req.method == "POST"
    assert req.url.path == "/api/v2/leads/list"
    assert body_of(req) == {"limit": 25, "filter": "FILTER_VAL_INTERESTED", "campaign": "camp", "contacts": ["a@b.co"]}


def test_analytics_endpoints():
    client, rec = make([(200, []), (200, []), (200, {}), (200, [])])
    client.campaign_analytics(ids=["c1"], start_date="2026-09-01", end_date="2026-09-21")
    client.daily_campaign_analytics("c1", "2026-09-01", "2026-09-21")
    client.warmup_analytics(["a@x.com", "b@x.com"])
    client.daily_account_analytics(emails=["a@x.com"], start_date="2026-09-01", end_date="2026-09-21")
    r0, r1, r2, r3 = rec.requests
    assert r0.url.path == "/api/v2/campaigns/analytics" and r0.url.params["id"] == "c1"
    assert r1.url.path == "/api/v2/campaigns/analytics/daily" and r1.url.params["campaign_id"] == "c1"
    assert r2.method == "POST" and r2.url.path == "/api/v2/accounts/warmup-analytics"
    assert body_of(r2) == {"emails": ["a@x.com", "b@x.com"]}
    assert r3.url.path == "/api/v2/accounts/analytics/daily"


def test_misc_read_paths():
    client, rec = make([(200, {"items": []}), (200, []), (200, {"items": []}), (200, {"items": []})])
    client.lead_labels_list()
    client.webhooks_list()
    client.subsequences_list("parent-1")
    client.list_accounts(limit=10)
    paths = [r.url.path for r in rec.requests]
    assert paths == ["/api/v2/lead-labels", "/api/v2/webhooks", "/api/v2/subsequences", "/api/v2/accounts"]
    assert rec.requests[2].url.params["parent_campaign"] == "parent-1"
    assert rec.requests[3].url.params["limit"] == "10"


def test_iterate_follows_cursor_get():
    client, rec = make([
        (200, {"items": [{"id": 1}, {"id": 2}], "next_starting_after": "cur1"}),
        (200, {"items": [{"id": 3}], "next_starting_after": None}),
    ])
    items = list(client.iterate("emails", {"email_type": "received", "limit": 2}))
    assert [i["id"] for i in items] == [1, 2, 3]
    assert "starting_after" not in rec.requests[0].url.params
    assert rec.requests[1].url.params["starting_after"] == "cur1"


def test_iterate_follows_cursor_post():
    client, rec = make([
        (200, {"items": [{"id": 1}], "next_starting_after": "cur1"}),
        (200, {"items": [{"id": 2}], "next_starting_after": "cur2"}),
        (200, {"items": [], "next_starting_after": None}),
    ])
    items = list(client.iterate("leads/list", body={"limit": 1, "campaign": "c"}))
    assert [i["id"] for i in items] == [1, 2]
    assert rec.requests[0].method == "POST"
    assert body_of(rec.requests[1])["starting_after"] == "cur1"


def test_iterate_continues_past_an_empty_page_that_still_has_a_cursor():
    """Instantly returns an empty-but-cursored page whenever a filter excludes
    everything on it; stopping there truncates the walk silently."""
    client, rec = make([
        (200, {"items": [{"id": "1"}], "next_starting_after": "c1"}),
        (200, {"items": [], "next_starting_after": "c2"}),
        (200, {"items": [{"id": "2"}], "next_starting_after": None}),
    ])
    items = list(client.iterate("leads/list", body={"limit": 100}))
    assert [i["id"] for i in items] == ["1", "2"]
    assert len(rec.requests) == 3
    assert body_of(rec.requests[2])["starting_after"] == "c2"


def test_iterate_accepts_a_bare_list_response():
    """GET /webhooks and several v2 reads answer with a bare JSON array."""
    client, rec = make([(200, [{"id": "wh_1"}, {"id": "wh_2"}])])
    items = list(client.iterate("webhooks"))
    assert [i["id"] for i in items] == ["wh_1", "wh_2"]
    assert len(rec.requests) == 1  # no cursor on an array: the walk ends


def test_iterate_stops_at_max_pages():
    client, rec = make([(200, {"items": [{"id": i}], "next_starting_after": "c%d" % i}) for i in range(10)])
    items = list(client.iterate("emails", {"limit": 1}, max_pages=3))
    assert [i["id"] for i in items] == [0, 1, 2]
    assert len(rec.requests) == 3


def test_retry_on_429_then_success():
    client, rec = make([
        httpx.Response(429, headers={"Retry-After": "0"}, json={"error": "rate"}),
        httpx.Response(429, json={"error": "rate"}),
        httpx.Response(200, json={"items": [{"id": "ok"}]}),
    ])
    out = client.list_campaigns()
    assert out["items"][0]["id"] == "ok"
    assert len(rec.requests) == 3


def test_retry_gives_up_after_max():
    client, rec = make([httpx.Response(429, json={}) for _ in range(5)])
    with pytest.raises(InstantlyError):
        client.list_campaigns()
    assert len(rec.requests) == 4  # 1 + 3 retries


def test_reads_retry_5xx_and_transport_errors():
    client, rec = make([
        httpx.Response(503, json={"error": "upstream"}),
        httpx.Response(200, json={"items": [{"id": "ok"}]}),
    ])
    assert client.list_campaigns()["items"][0]["id"] == "ok"
    assert len(rec.requests) == 2

    calls = {"n": 0}

    def flaky(request):
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectError("boom")
        return httpx.Response(200, json={"items": []})

    client2 = Instantly(api_key="k", transport=httpx.MockTransport(flaky), sleep=lambda s: None)
    assert client2.list_campaigns() == {"items": []}
    assert calls["n"] == 2


def test_backoff_is_capped_and_honours_retry_after():
    delays = []
    rec = Recorder([httpx.Response(429, headers={"Retry-After": "600"}, json={}),
                    httpx.Response(200, json={"items": []})])
    client = Instantly(api_key="k", transport=httpx.MockTransport(rec), sleep=delays.append)
    client.list_campaigns()
    assert delays == [60.0]  # Retry-After honoured, capped at MAX_BACKOFF_SECONDS


def test_writes_are_never_retried_on_429(tmp_env, live_mode):
    """A 429 can arrive after Instantly queued the send and there is no
    idempotency key, so one logical send must issue exactly one POST."""
    client, rec = make([httpx.Response(429, json={"error": "rate"}) for _ in range(5)])
    with pytest.raises(InstantlyError):
        client.reply_to_email("uuid-1", "lorenzo@myadvero.com", "Re: hi", "body", to="lead@x.com")
    assert len(rec.requests) == 1

    client2, rec2 = make([httpx.Response(429, json={}) for _ in range(5)])
    with pytest.raises(InstantlyError):
        client2.blocklist_create("hostile@x.com")
    assert len(rec2.requests) == 1

    client3, rec3 = make([httpx.Response(429, json={}) for _ in range(5)])
    with pytest.raises(InstantlyError):
        client3.update_campaign("camp-1", {"daily_limit": 10})
    assert len(rec3.requests) == 1


def test_post_shaped_reads_still_retry(tmp_env, live_mode):
    client, rec = make([httpx.Response(429, json={}), httpx.Response(200, json={"items": []})])
    assert client.list_leads(campaign="c") == {"items": []}
    assert len(rec.requests) == 2


def test_live_write_attempt_and_failure_are_recorded_in_the_job_log(tmp_env, live_mode):
    """A gateway 504 may still have enqueued the email; the run has to leave a
    row the operator can reconcile against."""
    import csv

    client, rec = make([httpx.Response(504, text="gateway timeout")])
    with pytest.raises(InstantlyError):
        client.reply_to_email("uuid-1", "lorenzo@myadvero.com", "Re: hi", "body", to="lead@x.com")
    with open(job_log.job_log_path(), newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    statuses = [r["status"] for r in rows if r["job"] == "instantly.reply_to_email"]
    assert statuses == ["live_write_intent", "live_write_failed"]
    assert "504" in rows[-1]["details"]


def test_live_write_ok_is_recorded(tmp_env, live_mode):
    import csv

    client, rec = make([(200, {"id": "sent"})])
    client.reply_to_email("uuid-1", "lorenzo@myadvero.com", "Re: hi", "body", to="lead@x.com")
    with open(job_log.job_log_path(), newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert [r["status"] for r in rows if r["job"] == "instantly.reply_to_email"] == [
        "live_write_intent", "live_write_ok",
    ]


def test_http_error_raises():
    client, rec = make([(400, {"message": "bad"})])
    with pytest.raises(InstantlyError) as exc:
        client.get_campaign("x")
    assert "400" in str(exc.value)


def test_missing_key_raises(monkeypatch):
    monkeypatch.delenv("INSTANTLY_API_KEY", raising=False)
    with pytest.raises(InstantlyError):
        Instantly(api_key=None, transport=httpx.MockTransport(Recorder()))


# ---------------------------------------------------- writes: shadow mode
WRITE_CALLS = [
    ("reply_to_email", ("uuid-1", "lorenzo@myadvero.com", "Re: hi", "body text"), {"to": "lead@x.com"}),
    ("update_interest_status", ("lead@x.com", "camp-1", 1), {}),
    ("update_lead", ("lead-1", {"first_name": "A"}), {}),
    ("update_campaign", ("camp-1", {"daily_limit": 10}), {}),
    ("pause_account", ("lorenzo@myadvero.com",), {}),
    ("resume_account", ("lorenzo@myadvero.com",), {}),
    ("lead_labels_create", ("positive_interested", "interested"), {"description": "d"}),
    ("webhooks_create", ({"target_hook_url": "https://x", "event_type": "reply_received"},), {}),
    ("subsequences_create", ({"parent_campaign": "c", "name": "s"},), {}),
    ("blocklist_create", ("hostile@x.com",), {}),
    ("move_to_subsequence", ("l1", "sub-1"), {}),
]


@pytest.mark.parametrize("name,args,kwargs", WRITE_CALLS)
def test_writes_make_no_request_in_shadow(tmp_env, shadow_mode, name, args, kwargs):
    client, rec = make()
    result = getattr(client, name)(*args, **kwargs)
    assert rec.requests == [], "%s must not hit the network in shadow" % name
    assert result["shadow"] is True
    assert result["system"] == "instantly"
    assert result["action"] == name
    rows = job_log.read_shadow_log()
    assert rows and rows[-1]["action"] == name


def test_reply_to_email_shadow_payload(tmp_env, shadow_mode):
    client, rec = make()
    res = client.reply_to_email("uuid-1", "lorenzo@myadvero.com", "Re: Sopio, question", "Hey Sopio,\n\nLorenzo",
                                to="sopiosvanishvili@taxfoaccounting.com")
    assert res["payload"]["reply_to_uuid"] == "uuid-1"
    assert res["payload"]["eaccount"] == "lorenzo@myadvero.com"
    assert res["payload"]["to"] == "sopiosvanishvili@taxfoaccounting.com"
    assert res["payload"]["body"]["text"].startswith("Hey Sopio")
    assert "<br>" in res["payload"]["body"]["html"]
    assert rec.requests == []


# ------------------------------------------------------ writes: live mode
def test_reply_to_email_live_request(tmp_env, live_mode):
    client, rec = make([(200, {"id": "sent"})])
    out = client.reply_to_email("uuid-1", "lorenzo@myadvero.com", "Re: hi", "text body",
                                body_html="<p>text body</p>", to="lead@x.com")
    assert out == {"id": "sent"}
    req = rec.requests[0]
    assert req.method == "POST"
    assert req.url.path == "/api/v2/emails/reply"
    assert body_of(req) == {
        "reply_to_uuid": "uuid-1",
        "eaccount": "lorenzo@myadvero.com",
        "subject": "Re: hi",
        "to": "lead@x.com",
        "body": {"text": "text body", "html": "<p>text body</p>"},
    }
    # live writes land in the job log, not the shadow log
    assert job_log.read_shadow_log() == []
    assert job_log.job_log_path().exists()


def test_reply_to_email_sends_to_for_recipient_validation(tmp_env, live_mode):
    """'to' is the expected recipient; Instantly checks it against the thread."""
    client, rec = make([(200, {"id": "sent"})])
    client.reply_to_email("uuid-1", "lorenzo@myadvero.com", "Re: hi", "text body", to="lead@x.com")
    body = body_of(rec.requests[0])
    assert body["to"] == "lead@x.com" and "skip_validation" not in body


def test_reply_to_email_without_to_is_refused_or_logged(tmp_env, live_mode):
    """Omitting `to` disables Instantly's recipient-vs-thread check, so the
    library refuses the send instead of letting a caller forget it."""
    client, rec = make([(200, {"id": "sent"})])
    with pytest.raises(InstantlyError) as exc:
        client.reply_to_email("uuid-1", "lorenzo@myadvero.com", "Re: hi", "text body")
    assert "to=" in str(exc.value)
    assert rec.requests == []          # nothing was sent
    assert job_log.read_shadow_log() == []
    # the deliberate opt-out is still available and is visible in the body
    client.reply_to_email("uuid-1", "lorenzo@myadvero.com", "Re: hi", "text body", skip_validation=True)
    assert body_of(rec.requests[0])["skip_validation"] is True


def test_reply_to_email_without_to_is_refused_in_shadow_too(tmp_env, shadow_mode):
    client, rec = make()
    with pytest.raises(InstantlyError):
        client.reply_to_email("uuid-1", "lorenzo@myadvero.com", "Re: hi", "text body")
    assert rec.requests == [] and job_log.read_shadow_log() == []


def test_move_leads_to_subsequence_is_one_call_per_lead(tmp_env, live_mode):
    client, rec = make([(200, {}), (200, {})])
    client.move_leads_to_subsequence(["l1", "l2"], "sub-1")
    assert [body_of(r) for r in rec.requests] == [
        {"id": "l1", "subsequence_id": "sub-1"},
        {"id": "l2", "subsequence_id": "sub-1"},
    ]


def test_update_interest_status_live(tmp_env, live_mode):
    client, rec = make([(200, {})])
    client.update_interest_status("lead@x.com", "camp-1", 2)
    req = rec.requests[0]
    assert req.method == "POST" and req.url.path == "/api/v2/leads/update-interest-status"
    assert body_of(req) == {"lead_email": "lead@x.com", "campaign_id": "camp-1", "interest_value": 2}


def test_patch_and_account_paths_live(tmp_env, live_mode):
    client, rec = make([(200, {}), (200, {}), (200, {}), (200, {})])
    client.update_campaign("camp-1", {"daily_limit": 10})
    client.update_lead("lead-1", {"first_name": "A"})
    client.pause_account("lorenzo@myadvero.com")
    client.resume_account("lorenzo@myadvero.com")
    r0, r1, r2, r3 = rec.requests
    assert (r0.method, r0.url.path) == ("PATCH", "/api/v2/campaigns/camp-1") and body_of(r0) == {"daily_limit": 10}
    assert (r1.method, r1.url.path) == ("PATCH", "/api/v2/leads/lead-1")
    assert (r2.method, r2.url.path) == ("POST", "/api/v2/accounts/lorenzo@myadvero.com/pause")
    assert (r3.method, r3.url.path) == ("POST", "/api/v2/accounts/lorenzo@myadvero.com/resume")


def test_daily_account_analytics_requires_an_emails_filter(tmp_env, monkeypatch):
    """This workspace answers HTTP 413 without an emails filter, even for a
    two-day range (verified read-only 2026-09-21)."""
    from shared import settings

    client, rec = make([(200, [{"date": "2026-09-20"}])])
    client.daily_account_analytics(start_date="2026-09-20", end_date="2026-09-21")
    params = rec.requests[0].url.params
    active = settings.IDS["instantly"]["active_inboxes"]
    assert params.get_list("emails") == active  # defaulted to the active inboxes

    # nothing to default to -> a clear error instead of a 413 from the gateway
    monkeypatch.setattr(settings, "IDS", {"instantly": {}})
    client2, rec2 = make()
    with pytest.raises(InstantlyError) as exc:
        client2.daily_account_analytics(start_date="2026-09-20", end_date="2026-09-21")
    assert "413" in str(exc.value) and "emails" in str(exc.value)
    assert rec2.requests == []


def test_daily_account_analytics_413_body_is_surfaced(tmp_env):
    client, rec = make([(413, {"message": "Analytics request is too large for this workspace"})])
    with pytest.raises(InstantlyError) as exc:
        client.daily_account_analytics(emails=["lorenzo@adveromedia.com"])
    assert "413" in str(exc.value) and "too large" in str(exc.value)


def test_update_interest_status_rejects_a_code_not_in_ids_json(tmp_env, live_mode):
    client, rec = make([(200, {}), (200, {})])
    for bad in (99, 5):
        with pytest.raises(InstantlyError) as exc:
            client.update_interest_status("a@b.com", "camp", bad)
        assert "interest code" in str(exc.value)
    assert rec.requests == []
    # -4 (no_show) is a real code and must be accepted
    client.update_interest_status("a@b.com", "camp", -4)
    assert body_of(rec.requests[0])["interest_value"] == -4


def test_blocklist_create_shadow_payload_matches_the_live_body(tmp_env, monkeypatch):
    """The shadow log is only useful before go-live if it records the request
    that live mode would actually make."""
    monkeypatch.setenv("MODE", "shadow")
    monkeypatch.delenv("ALLOW_LIVE_WRITES", raising=False)
    client, rec = make()
    guarded = client.blocklist_create("spam.com", type="domain")["payload"]
    assert rec.requests == []

    monkeypatch.setenv("MODE", "live")
    monkeypatch.setenv("ALLOW_LIVE_WRITES", "1")
    client2, rec2 = make([(200, {})])
    client2.blocklist_create("spam.com", type="domain")
    assert guarded == body_of(rec2.requests[0]) == {"bl_value": "spam.com"}


def test_label_webhook_subsequence_blocklist_live(tmp_env, live_mode):
    client, rec = make([(200, {}), (200, {}), (200, {}), (200, {}), (200, {})])
    client.lead_labels_create("positive_interested", "interested", description="wants a call")
    client.webhooks_create({"target_hook_url": "https://x", "event_type": "reply_received"})
    client.subsequences_create({"parent_campaign": "c", "name": "s"})
    client.blocklist_create("hostile@x.com")
    client.move_to_subsequence("l1", "sub-1")
    r0, r1, r2, r3, r4 = rec.requests
    assert r0.url.path == "/api/v2/lead-labels"
    assert body_of(r0) == {"label": "positive_interested", "interest_status_label": "interested", "description": "wants a call", "use_with_ai": True}
    assert r1.url.path == "/api/v2/webhooks" and body_of(r1)["event_type"] == "reply_received"
    assert r2.url.path == "/api/v2/subsequences"
    assert r3.url.path == "/api/v2/block-lists-entries" and body_of(r3) == {"bl_value": "hostile@x.com"}
    assert r4.url.path == "/api/v2/leads/subsequence/move" and body_of(r4) == {"id": "l1", "subsequence_id": "sub-1"}


def test_webhooks_create_pins_the_target_field_name(tmp_env, shadow_mode):
    """config/instantly_api_contract.md: the only required property is
    `target_hook_url`. `target_url` is not rejected by the API, it just creates
    a webhook with no target, so every reply is silently never delivered.
    runbooks/deployment.md said `target_url` once already."""
    client = Instantly(api_key="k", transport=httpx.MockTransport(Recorder()))
    rec = client.webhooks_create({"target_hook_url": "https://x.modal.run/webhooks/instantly",
                                  "event_type": "reply_received"})
    assert rec["payload"]["target_hook_url"] == "https://x.modal.run/webhooks/instantly"
    assert "target_url" not in rec["payload"]

    # the wrong key is corrected, not sent
    rec = client.webhooks_create({"target_url": "https://x.modal.run/webhooks/instantly",
                                  "event_type": "reply_received"})
    assert rec["payload"] == {"target_hook_url": "https://x.modal.run/webhooks/instantly",
                              "event_type": "reply_received"}

    # and a payload with no usable target never reaches the API
    with pytest.raises(InstantlyError) as exc:
        client.webhooks_create({"event_type": "reply_received"})
    assert "target_hook_url" in str(exc.value)
