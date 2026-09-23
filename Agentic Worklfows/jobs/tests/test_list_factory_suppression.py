"""Suppression: built read-only, fail-closed, and checked against every
address the lead could be mailed at."""
import json

import httpx
import pytest

from shared.instantly import Instantly

from services.list_factory import models
from services.list_factory import suppression as supp_mod

MANUAL = {
    "client_domains": ["bigclient.com"],
    "manual_domains": ["gmail.com"],
    "manual_emails": ["never@example.com"],
}

WORKSPACE = [
    {"email": "angie@5starjanitor.com", "company_domain": "5starjanitor.com", "status": 3},
    {"email": "bounced@deadco.com", "company_domain": "deadco.com", "status": -1},
    {"email": "gone@optout.com", "company_domain": "optout.com", "status": -2},
    {"email": "active@stillgoing.com", "company_domain": "stillgoing.com", "status": 1},
]
BLOCKLIST = [
    {"bl_value": "robert@christiansonco.com", "is_domain": False},
    {"bl_value": "wholedomain.com", "is_domain": True},
]
RECEIVED = [
    {"from_address_email": "angry@hostile.com", "subject": "re: quick question",
     "content_preview": "Take me off your list and do not contact us again."},
    {"from_address_email": "polite@interested.com", "subject": "re: quick question",
     "content_preview": "Sure, what does this look like?"},
]


def make_client(workspace=None, blocklist=None, received=None, fail=None, pages=1):
    """MockTransport that answers the three read endpoints the builder uses."""
    workspace = WORKSPACE if workspace is None else workspace
    blocklist = BLOCKLIST if blocklist is None else blocklist
    received = RECEIVED if received is None else received
    state = {"leads_page": 0}

    def handler(request):
        path = request.url.path
        if fail and fail in path:
            return httpx.Response(500, json={"error": "boom"})
        if path.endswith("/leads/list"):
            state["leads_page"] += 1
            body = {"items": workspace}
            # `pages` > 1 keeps the cursor open forever, which is what a
            # truncated walk looks like.
            if pages > 1:
                body["next_starting_after"] = "cursor-%d" % state["leads_page"]
            return httpx.Response(200, json=body)
        if path.endswith("/block-lists-entries"):
            return httpx.Response(200, json={"items": blocklist})
        if path.endswith("/emails"):
            return httpx.Response(200, json={"items": received})
        return httpx.Response(404, json={"error": path})

    return Instantly(api_key="test", transport=httpx.MockTransport(handler))


def lead(**kw):
    base = {"company_name": "Acme", "website": "https://acme.com"}
    base.update(kw)
    out = models.new_lead(base, source="test")
    out["email_candidates"] = kw.get("_candidates") or []
    out["email"] = kw.get("_email") or ""
    return out


def test_build_pulls_every_source_and_is_complete():
    supp = supp_mod.build(make_client(), manual=MANUAL)
    assert supp.complete, supp.errors
    assert "angie@5starjanitor.com" in supp.emails
    assert "bounced@deadco.com" in supp.emails
    assert "robert@christiansonco.com" in supp.emails
    assert "angry@hostile.com" in supp.emails
    assert "wholedomain.com" in supp.domains
    assert "bigclient.com" in supp.domains
    assert "gmail.com" in supp.domains
    assert "5starjanitor.com" in supp.domains


def test_reasons_are_specific_enough_to_review():
    supp = supp_mod.build(make_client(), manual=MANUAL)
    assert supp.reasons["email:bounced@deadco.com"] == "bounced in Instantly"
    assert supp.reasons["email:gone@optout.com"] == "unsubscribed in Instantly"
    assert supp.reasons["email:angry@hostile.com"] == "hostile or opt-out reply"
    assert supp.reasons["domain:bigclient.com"] == "client or our own sending domain"


def test_a_polite_reply_is_not_suppressed():
    supp = supp_mod.build(make_client(), manual=MANUAL)
    assert "polite@interested.com" not in supp.emails


def test_a_failed_source_makes_the_list_incomplete_and_staging_refuses():
    supp = supp_mod.build(make_client(fail="block-lists-entries"), manual=MANUAL)
    assert not supp.complete
    assert any("blocklist" in e for e in supp.errors)
    with pytest.raises(supp_mod.SuppressionError):
        supp.require_complete()


def test_a_truncated_workspace_walk_makes_the_list_incomplete():
    """The failure that matters: a partial pull looks exactly like a complete
    one, so the walk's own truncated flag is the only thing that can tell."""
    supp = supp_mod.build(make_client(pages=999), manual=MANUAL)
    assert not supp.complete
    assert any("truncated" in e for e in supp.errors)


def test_apply_refuses_to_run_on_an_incomplete_list():
    supp = supp_mod.build(make_client(fail="leads/list"), manual=MANUAL)
    with pytest.raises(supp_mod.SuppressionError):
        supp_mod.apply([lead()], supp)


def test_a_candidate_address_is_checked_even_when_it_is_not_the_verified_one():
    """A company whose first@ bounced is not made fresh by guessing
    first.last@ instead."""
    # christiansonco.com is on the blocklist by ADDRESS only, so the domain
    # rule cannot catch it; the candidate list is the only thing that can.
    supp = supp_mod.build(make_client(), manual=MANUAL)
    assert "christiansonco.com" not in supp.domains
    l = lead(website="https://christiansonco.com",
             _candidates=["robert@christiansonco.com", "r.christianson@christiansonco.com"])
    assert supp.check(l) == "on the Instantly blocklist"


def test_domain_suppression_catches_a_second_contact_at_a_contacted_company():
    supp = supp_mod.build(make_client(), manual=MANUAL)
    l = lead(website="https://5starjanitor.com", _candidates=["someoneelse@5starjanitor.com"])
    assert "already contacted" in (supp.check(l) or "")


def test_apply_rejects_and_advances_correctly():
    supp = supp_mod.build(make_client(), manual=MANUAL)
    suppressed = lead(website="https://5starjanitor.com")
    clean = lead(website="https://brandnewco.com", _candidates=["ann@brandnewco.com"])
    summary = supp_mod.apply([suppressed, clean], supp)
    assert summary["suppressed"] == 1
    assert summary["passed"] == 1
    assert models.is_rejected(suppressed)
    assert suppressed["reject_reason"] == models.REJECT_SUPPRESSED
    assert clean["stage"] == models.SUPPRESSED_CHECK


def test_hostile_marker_detection():
    assert supp_mod.is_hostile("please REMOVE ME from this list")
    assert supp_mod.is_hostile("Do not contact us again")
    assert supp_mod.is_hostile("this is spam, I will report you")
    assert not supp_mod.is_hostile("Sure, send me some info")
    assert not supp_mod.is_hostile("")


def test_cache_round_trips_and_an_incomplete_list_is_never_cached(tmp_path):
    good = supp_mod.build(make_client(), manual=MANUAL)
    path = str(tmp_path / "supp.json")
    supp_mod.save_cache(good, path)
    back = supp_mod.load_cached(path)
    assert back is not None
    assert back.complete
    assert back.emails == good.emails
    assert back.domains == good.domains
    assert back.check(lead(website="https://5starjanitor.com"))


def test_builder_only_ever_reads(monkeypatch):
    """Every request the builder makes must be a GET or the one read-shaped
    POST. A write slipping in here would reach live data on a --now run."""
    seen = []

    def handler(request):
        seen.append((request.method, request.url.path))
        if request.url.path.endswith("/leads/list"):
            return httpx.Response(200, json={"items": WORKSPACE})
        return httpx.Response(200, json={"items": []})

    client = Instantly(api_key="test", transport=httpx.MockTransport(handler))
    supp_mod.build(client, manual=MANUAL)
    for method, path in seen:
        assert method == "GET" or path.endswith("/leads/list"), (method, path)


def test_the_real_opt_outs_from_the_workspace_all_fire():
    """Verbatim from the 115 received replies in the live workspace
    (read-only, 2026-09-22). All 13 opt-outs there matched; these are them."""
    for text in (
        "For the love of god leave me alone",
        "Please don't email me again",
        "Remove me from email",
        "UNSUBSCRIBE",
        "My responses are fast. Please do not email me anymore.",
        "Take me off this list please",
        "UNSUBSCRIBE. PLEASE REMOVE MY EMAIL FROM YOUR LIST.",
        "NO! Remove me from your list!!!",
        "please remove me from your email list.",
    ):
        assert supp_mod.is_hostile(text), text


def test_a_reply_about_the_spam_folder_is_not_treated_as_hostile():
    """Someone who says the email landed in spam has read it. Suppressing them
    throws away a lead and a deliverability signal in one move."""
    assert not supp_mod.is_hostile("Found this in my spam folder, what is it?")
    assert not supp_mod.is_hostile("your emails keep going to the spam folder fyi")
    # ... but someone who says they are reporting us is.
    assert supp_mod.is_hostile("I am marking this as spam")
    assert supp_mod.is_hostile("this is spam, stop")


def test_ordinary_replies_never_fire():
    for text in (
        "Sure, what does this look like?",
        "Can you send some more info?",
        "I am out of the office until Monday.",
        "Not right now, try me in Q2.",
    ):
        assert not supp_mod.is_hostile(text), text


# =====================================================================
# Regressions from the 2026-09-22 review.
# =====================================================================
import os
from datetime import datetime, timedelta, timezone

RECORDED = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "services", "list_factory", "fixtures", "received_emails_recorded.json",
)


def _fresh(supp, hours_old=0.0):
    supp.built_utc = (datetime.now(timezone.utc) - timedelta(hours=hours_old)) \
        .replace(microsecond=0).isoformat()
    return supp


# ----------------------------------------------------------------- freshness
def test_a_stale_cached_list_is_refused_like_an_incomplete_one():
    """built_utc was stored and never read, so a 16-week-old file passed the
    fail-closed check exactly like a fresh one. Every address that
    unsubscribed, bounced or replied hostile in between got mailed again."""
    supp = _fresh(supp_mod.build(make_client(), manual=MANUAL), hours_old=40 * 24)
    assert supp.complete
    supp.require_complete()                       # no age limit: still fine
    with pytest.raises(supp_mod.SuppressionError) as exc:
        supp.require_complete(max_age_hours=24.0)
    assert "hours old" in str(exc.value)
    # ... and a fresh one passes.
    _fresh(supp).require_complete(max_age_hours=24.0)


def test_a_list_with_no_build_stamp_cannot_prove_it_is_fresh():
    supp = supp_mod.build(make_client(), manual=MANUAL)
    supp.built_utc = ""
    with pytest.raises(supp_mod.SuppressionError) as exc:
        supp.require_complete(max_age_hours=24.0)
    assert "no built_utc" in str(exc.value)


def test_apply_refuses_a_stale_list_before_it_suppresses_anything():
    supp = _fresh(supp_mod.build(make_client(), manual=MANUAL), hours_old=100)
    with pytest.raises(supp_mod.SuppressionError):
        supp_mod.apply([lead()], supp, max_age_hours=24.0)


# ------------------------------------------------------------- skipped source
def test_skipping_the_hostile_scan_makes_the_list_incomplete():
    """--skip-hostile-scan dropped a mandatory source but left complete=True,
    so the fail-closed guarantee was silently bypassed."""
    supp = supp_mod.build(make_client(), manual=MANUAL, read_emails=False)
    assert not supp.complete
    assert supp.skipped_sources == ["hostile_replies"]
    with pytest.raises(supp_mod.SuppressionError):
        supp.require_complete()


def test_a_skipped_source_list_is_never_written_to_the_day_cache(tmp_path, monkeypatch):
    """A later run in the same day that did NOT pass the flag would reuse the
    hostile-free list."""
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    supp_mod.get(make_client(), refresh=True, manual=MANUAL, read_emails=False)
    assert supp_mod.load_cached() is None
    supp_mod.get(make_client(), refresh=True, manual=MANUAL, read_emails=True)
    assert supp_mod.load_cached() is not None


# ----------------------------------------------------------- hostile matching
def test_was_spam_filtered_is_not_a_spam_report():
    """`marker in blob` made "was spam filtered" hit the "as spam" marker, and
    a warm prospect plus every colleague at their domain were suppressed."""
    assert not supp_mod.is_hostile(
        "Heads up, your first note was spam filtered but I dug it out. What does this look like?")
    assert supp_mod.is_hostile("This has been marked as spam.")


def test_a_quoted_unsubscribe_footer_does_not_suppress_a_warm_reply():
    reply = (
        "Sounds interesting, send me pricing.\n\n"
        "On Wed, Sep 16, 2026 at 6:42 AM Lorenzo Villarreal <lorenzo@example.com> wrote:\n"
        "> Hey Ann, saw that you do commercial cleaning.\n"
        "> Unsubscribe here: https://example.com/u\n"
    )
    assert not supp_mod.is_hostile(reply)


def test_an_outlook_style_quote_is_stripped_too():
    reply = (
        "Sure, happy to talk.\n"
        "________________________________\n"
        "From: Lorenzo Villarreal <lorenzo@example.com>\n"
        "Sent: 15 September 2026\n"
        "Subject: quick question\n"
        "Unsubscribe: https://example.com/u\n"
    )
    assert not supp_mod.is_hostile(reply)


def test_an_automatic_reply_is_not_an_opt_out():
    """info@theaugustacpa.com's standard CPA footer says "please do not email
    documents containing sensitive information"; the bare "do not email" marker
    suppressed the firm and its whole domain, in the one niche where that
    footer is industry boilerplate."""
    body = (
        "Thank you for reaching out to Summerville Tax & Accounting LLC. "
        "NOTE: Please do not email documents containing sensitive and/or confidential "
        "information, including, but not limited to SSNs, EINs, bank account numbers."
    )
    assert not supp_mod.is_hostile(body, subject="Automatic reply: Stefanie, question")
    # ... and the phrase is anchored on the sender's own intent, so it does not
    # fire even without the subject.
    assert not supp_mod.is_hostile(body)
    assert supp_mod.is_hostile("Please do not email me anymore. I am not interested.")


def test_instantly_ue_type_cannot_be_used_to_spot_an_auto_reply():
    """Every one of the 115 received rows in the live workspace carries
    ue_type == 2, so filtering on it would suppress nobody at all. Pinned here
    because it is the obvious fix and it is wrong."""
    rows = json.load(open(RECORDED, "r", encoding="utf-8"))
    assert rows, RECORDED
    assert {r.get("ue_type") for r in rows} == {2}


def test_the_recorded_replies_produce_exactly_the_opt_outs():
    """All 115 received replies, read read-only on 2026-09-22. The old list
    fired on 16 rows, one of them an automatic reply."""
    rows = json.load(open(RECORDED, "r", encoding="utf-8"))
    hits = []
    for row in rows:
        body = row.get("body")
        text = body if isinstance(body, str) else (body or {}).get("text") or ""
        blob = "%s\n%s" % (models.clean_text(row.get("content_preview")), text)
        if supp_mod.is_hostile(blob, subject=row.get("subject")):
            hits.append(row.get("from_address_email"))
    assert len(rows) == 115
    assert len(hits) == 15, hits
    assert len(set(hits)) == 14, "aaron@truebondroofing.com opted out twice"
    assert "info@theaugustacpa.com" not in hits, "an out-of-office is not an opt-out"
    for opt_out in ("dvent@intraview.io", "david@meadeshvac.com", "stacy@slkroofing.com",
                    "ron.daniels@siteforce.us", "maggie@northwestsnowremoval.com"):
        assert opt_out in hits, opt_out


def test_every_hostile_hit_names_the_marker_that_fired():
    supp = supp_mod.build(make_client(), manual=MANUAL)
    hits = supp.sources["hostile_replies"]["hits"]
    assert hits
    assert hits[0]["from"] == "angry@hostile.com"
    assert hits[0]["markers"]
    assert supp.sources["hostile_replies"]["senders"] == 1


# ------------------------------------------------------------ the free half
def test_check_domain_is_the_free_half_of_check():
    supp = supp_mod.build(make_client(), manual=MANUAL)
    by_domain = lead(website="https://5starjanitor.com")
    assert supp.check_domain(by_domain)
    # An address-only blocklist entry is invisible to the domain-only pass,
    # which is exactly why the address check still runs after verification.
    by_address = lead(website="https://christiansonco.com",
                      _candidates=["robert@christiansonco.com"])
    assert supp.check_domain(by_address) is None
    assert supp.check(by_address)


def test_a_domain_only_pass_leaves_the_lead_pending_for_the_address_pass():
    supp = supp_mod.build(make_client(), manual=MANUAL)
    clean = lead(website="https://brandnewco.com", _candidates=["ann@brandnewco.com"])
    summary = supp_mod.apply([clean], supp, domain_only=True)
    assert summary["passed"] == 1
    assert summary["domain_only"] is True
    assert clean["stage"] != models.SUPPRESSED_CHECK, "the address half has not run yet"
