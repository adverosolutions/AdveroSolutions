"""F4: the cadence decision links confirm on GET and act only on POST.

/cadence/veto (the D1 30-minute Veto), /cadence/approve (the D6 "Send hold")
and /cadence/veto-invite (the D6 "Email only") used to record the decision on
a plain GET. Email link scanners and chat previewers fetch URLs with GET, so a
scanner could record a signed decision with no human involved, and for
/cadence/approve that puts a calendar hold in front of a lead.

What is pinned here:

* GET with a valid token renders a confirmation page whose one button POSTs
  to the same path with the token, names no lead and changes no state;
* GET with a missing, forged, expired or wrong-kind token, with an unknown
  lead or with no signing secret is a neutral 403 with no lead data;
* POST with a valid token records exactly what the old GET recorded, and the
  next tick acts on it as before;
* POST with a bad token writes nothing, so it cannot overwrite a real
  decision the tick acts on;
* the pushed card's actions are ntfy ``view`` actions that open the page.

Every lead here is invented. Live mode is set in-process only and every
client is an in-process fake: nothing leaves the process.
"""
import re
from urllib.parse import unquote, urljoin, urlsplit

import pytest
from fastapi.testclient import TestClient

from shared import notify
from shared.store import JsonFileStore

from services.reply_engine import app as app_mod
from services.reply_engine import cadence
from services.reply_engine.models import LeadState

from test_send_safety_round2 import FakeInstantly, Recorder, _go_live, ct

BASE = "https://engine.test"
LEAD = "pat.quill@example-cleaning.test"
FIRST = "Pat"
COMPANY = "Quillfield Facility Group"
OTHER = "sam.otter@example-cleaning.test"
CAMPAIGN = "8086b41e-b546-4b36-9fa0-2d01f5cc119a"
D1_FREE = ["2026-09-23T13:00:00-05:00", "2026-09-24T14:00:00-05:00"]
D6_FREE = ["2026-09-29T13:00:00-05:00", "2026-09-30T14:00:00-05:00"]
KINDS = ("veto", "approve", "veto-invite")
BUTTON = {"veto": "Veto", "approve": "Send hold", "veto-invite": "Email only"}


def _new_state(email=LEAD, first=FIRST, company=COMPANY):
    state = LeadState(
        lead_email=email, campaign_id=CAMPAIGN, status="positive_interested", first_name=first,
        company=company, eaccount="lorenzo@adveromedia.com", thread_id="thr-f4", last_email_id="e-f4",
        last_subject="Re: %s, question" % first, ghl_contact_id="contact-f4")
    return cadence.arm(state, ct(2026, 9, 21, 16, 0))   # D1 due Tue 22nd 10:00


@pytest.fixture
def world(tmp_env, monkeypatch):
    monkeypatch.setenv("REPLY_ENGINE_SECRET", "unit-secret")
    monkeypatch.setenv("BASE_URL", BASE)
    monkeypatch.delenv("REPLY_ENGINE_BASE_URL", raising=False)
    notify.reset_for_tests()
    store = JsonFileStore(tmp_env / "store.json")
    clock = {"now": ct(2026, 9, 22, 9, 35)}
    app_mod.configure(store=store, ghl=Recorder(), instantly=FakeInstantly(sender=LEAD), clock=lambda: clock["now"])
    state = _new_state()
    store.set(state.key, state.to_store())
    yield {"store": store, "clock": clock, "client": TestClient(app_mod.app), "state": state}
    app_mod.configure()


def _path(url):
    """The path and query of an absolute card URL, for the TestClient."""
    parts = urlsplit(url)
    return "%s?%s" % (parts.path, parts.query) if parts.query else parts.path


def _link(world, kind, minted=None, state=None):
    return _path(cadence._decision_url(kind, state or world["state"], minted or ct(2026, 9, 22, 9, 30)))


def _snapshot(store):
    return store._read()


def _record_key(kind, state):
    return cadence.veto_key(state) if kind == "veto" else cadence.approval_key(state, "d6")


def _form_target(page_url, html):
    """Where the confirmation page's one form posts, resolved like a browser."""
    forms = re.findall(r"<form method='post' action='([^']*)'>", html)
    assert len(forms) == 1, html
    return _path(urljoin(BASE + page_url, forms[0].replace("&amp;", "&")))


def _assert_no_lead_data(text):
    """No address, name, company, campaign or store key ("lead:<campaign>:...")."""
    for leak in (LEAD, FIRST, COMPANY, CAMPAIGN, "example-cleaning", "nobody"):
        assert leak not in text, leak


def _live_tick(store, when, free, monkeypatch, pings=None, ghl=None, inst=None):
    _go_live(monkeypatch)
    state = LeadState.from_store(store.get("lead:%s:%s" % (CAMPAIGN, LEAD)))
    res = cadence.tick_lead(state, when, store=store, instantly=inst or FakeInstantly(sender=LEAD), ghl=ghl,
                            free_slots=free,
                            notify_fn=lambda *a, **k: (pings.append((a, k)) if pings is not None else None)
                            or {"sent": True, "email": True})
    store.set(state.key, state.to_store())
    return res, state


# ------------------------------------------------------------------ GET
@pytest.mark.parametrize("kind", KINDS)
def test_get_with_a_valid_token_renders_a_confirm_page_and_changes_nothing(world, kind):
    before = _snapshot(world["store"])
    url = _link(world, kind)
    r = world["client"].get(url)
    assert r.status_code == 200
    assert "<form method='post'" in r.text and ">%s</button>" % BUTTON[kind] in r.text
    assert "Nothing is recorded until you press %s" % BUTTON[kind] in r.text
    _assert_no_lead_data(r.text)
    # the one button posts to the same path, with the same token
    assert _form_target(url, r.text) == url
    # a second fetch (a scanner, a previewer, a browser prefetch) is just as inert
    assert world["client"].get(url).status_code == 200
    assert world["client"].head(url).status_code in (200, 405)
    assert _snapshot(world["store"]) == before
    assert world["store"].get(_record_key(kind, world["state"])) is None
    assert notify.sent_in_test == []


def _bad_links(world, kind):
    state = world["state"]
    good = cadence.make_decision_token(kind, state, ct(2026, 9, 22, 9, 30))
    other_kind = [k for k in KINDS if k != kind][0]
    path = "/cadence/%s/%s/%s" % (kind, CAMPAIGN, LEAD)
    return {
        "missing": path,
        "empty": path + "?t=",
        "garbage": path + "?t=garbage",
        "forged": path + "?t=" + good.rsplit(".", 1)[0] + ".deadbeefdeadbeefdeadbeefdeadbeef",
        "expired": _link(world, kind, minted=ct(2026, 9, 20, 8, 0)),
        "wrong_kind": path + "?t=" + cadence.make_decision_token(other_kind, state, ct(2026, 9, 22, 9, 30)),
        "other_lead": path + "?t=" + cadence.make_decision_token(kind, _new_state(OTHER, "Sam", "Otter Co"),
                                                                 ct(2026, 9, 22, 9, 30)),
        "unknown_lead": "/cadence/%s/%s/%s?t=%s" % (kind, CAMPAIGN, "nobody@example-cleaning.test", good),
    }


@pytest.mark.parametrize("kind", KINDS)
def test_get_with_a_bad_token_or_an_unknown_lead_is_a_neutral_403(world, kind):
    before = _snapshot(world["store"])
    bodies = set()
    for name, url in _bad_links(world, kind).items():
        r = world["client"].get(url)
        assert r.status_code == 403, name
        assert "Not recorded" in r.text and "<form" not in r.text, name
        _assert_no_lead_data(r.text)
        bodies.add(r.text)
    # one page for every refusal: it does not say whether the lead exists
    assert len(bodies) == 1
    assert _snapshot(world["store"]) == before


@pytest.mark.parametrize("kind", KINDS)
def test_get_with_no_signing_secret_is_a_neutral_403(world, kind, monkeypatch):
    url = _link(world, kind)
    monkeypatch.delenv("REPLY_ENGINE_SECRET")
    before = _snapshot(world["store"])
    for u in (url, url.split("?")[0]):
        r = world["client"].get(u)
        assert r.status_code == 403 and "Not recorded" in r.text
        _assert_no_lead_data(r.text)
        assert world["client"].post(u).status_code == 403
    assert _snapshot(world["store"]) == before


def test_an_escaped_path_segment_is_not_reflected(world):
    r = world["client"].get("/cadence/veto/%s/%s" % (CAMPAIGN, "%3Cimg%20src%3Dx%20onerror%3Dalert(1)%3E@x.com"))
    assert r.status_code == 403 and "<img" not in r.text and "&lt;img" not in r.text and CAMPAIGN not in r.text


# ----------------------------------------------------------------- POST
OLD_PAGE = {"veto": "Touch vetoed", "approve": "Invite approved", "veto-invite": "Invite vetoed"}


def _old_record(kind, state, now, token, tmp_path):
    """What the old GET recorded: the cadence recorder called straight with the token."""
    scratch = JsonFileStore(tmp_path / ("old-%s.json" % kind))
    if kind == "veto":
        return cadence.record_veto(scratch, state, now, token=token)
    return cadence.record_invite_decision(scratch, state, "approve" if kind == "approve" else "veto", now, token=token)


@pytest.mark.parametrize("kind", KINDS)
def test_post_with_a_valid_token_records_what_the_old_get_recorded(world, kind, tmp_path):
    url = _link(world, kind)
    confirm = world["client"].get(url)
    r = world["client"].post(_form_target(url, confirm.text))
    assert r.status_code == 200 and OLD_PAGE[kind] in r.text
    token = url.split("?t=", 1)[1]
    expected = _old_record(kind, world["state"], world["clock"]["now"], unquote(token), tmp_path)
    got = world["store"].get(_record_key(kind, world["state"]))
    assert got == expected
    assert got["token_ok"] is True and got["armed_at"] == world["state"].cadence["armed_at"]
    if kind != "veto":
        assert got["decision"] == ("approve" if kind == "approve" else "veto")


def test_a_posted_veto_stops_d1_on_the_next_tick(world, monkeypatch):
    pings = []
    res, _ = _live_tick(world["store"], ct(2026, 9, 22, 9, 30), D1_FREE, monkeypatch, pings)
    assert res["action"] == "veto_window_opened"
    url = _path(pings[-1][1]["actions"][0][1])
    page = world["client"].get(url)
    assert page.status_code == 200
    assert world["client"].post(_form_target(url, page.text)).status_code == 200
    inst = FakeInstantly(sender=LEAD)
    res, state = _live_tick(world["store"], ct(2026, 9, 22, 10, 0), D1_FREE, monkeypatch, inst=inst)
    assert res["action"] == "vetoed" and state.cadence["stopped_reason"] == "vetoed"
    assert inst.sent == []


def test_a_d1_veto_window_link_only_opened_sends_as_before(world, monkeypatch):
    """Opening the Veto page without pressing Veto is not a veto."""
    pings = []
    res, _ = _live_tick(world["store"], ct(2026, 9, 22, 9, 30), D1_FREE, monkeypatch, pings)
    assert world["client"].get(_path(pings[-1][1]["actions"][0][1])).status_code == 200
    inst = FakeInstantly(sender=LEAD)
    res, _ = _live_tick(world["store"], ct(2026, 9, 22, 10, 0), D1_FREE, monkeypatch, inst=inst)
    assert res["action"] == "sent" and len(inst.sent) == 1


def _d6_ready(world):
    state = LeadState.from_store(world["store"].get(world["state"].key))
    state.cadence["day"] = 5
    state.cadence["next_send_at"] = ct(2026, 9, 28, 10, 0).isoformat()
    world["store"].set(state.key, state.to_store())
    world["clock"]["now"] = ct(2026, 9, 28, 10, 5)
    return state


def _d6_card(world, monkeypatch):
    monkeypatch.setenv("CADENCE_D6_HOLD", "1")
    _d6_ready(world)
    pings = []
    res, _ = _live_tick(world["store"], ct(2026, 9, 28, 10, 0), D6_FREE, monkeypatch, pings)
    assert res["action"] == "awaiting_invite_ok"
    return dict((label, _path(url)) for label, url in pings[-1][1]["actions"])


def test_a_posted_send_hold_books_the_hold_and_sends_d6(world, monkeypatch):
    links = _d6_card(world, monkeypatch)
    page = world["client"].get(links["Send hold"])
    assert page.status_code == 200
    assert world["client"].post(_form_target(links["Send hold"], page.text)).status_code == 200
    ghl, inst = Recorder(), FakeInstantly(sender=LEAD)
    res, _ = _live_tick(world["store"], ct(2026, 9, 28, 10, 10), D6_FREE, monkeypatch, ghl=ghl, inst=inst)
    assert res["action"] == "sent" and res["day"] == 6
    assert len(ghl.named("create_appointment")) == 1 and len(inst.sent) == 1


def test_a_posted_email_only_sends_d6_without_a_hold(world, monkeypatch):
    links = _d6_card(world, monkeypatch)
    page = world["client"].get(links["Email only"])
    assert world["client"].post(_form_target(links["Email only"], page.text)).status_code == 200
    ghl, inst = Recorder(), FakeInstantly(sender=LEAD)
    res, _ = _live_tick(world["store"], ct(2026, 9, 28, 10, 10), D6_FREE, monkeypatch, ghl=ghl, inst=inst)
    assert res["action"] == "sent" and res["day"] == 6
    assert ghl.named("create_appointment") == [] and len(inst.sent) == 1


def test_opening_the_d6_pages_without_pressing_leaves_the_day_waiting(world, monkeypatch):
    links = _d6_card(world, monkeypatch)
    for url in links.values():
        assert world["client"].get(url).status_code == 200
    ghl = Recorder()
    res, _ = _live_tick(world["store"], ct(2026, 9, 28, 11, 0), D6_FREE, monkeypatch, ghl=ghl)
    assert res["action"] == "awaiting_invite_ok" and ghl.calls == []


@pytest.mark.parametrize("kind", KINDS)
def test_post_with_a_bad_token_writes_nothing(world, kind):
    before = _snapshot(world["store"])
    for name, url in _bad_links(world, kind).items():
        r = world["client"].post(url)
        assert r.status_code == 403, name
        _assert_no_lead_data(r.text)
    assert _snapshot(world["store"]) == before
    assert world["store"].get(_record_key(kind, world["state"])) is None


def test_a_forged_post_cannot_overwrite_a_real_veto(world, monkeypatch):
    """The old route wrote a token_ok=False record at the same key, which the
    tick ignores: a forged request after Lorenzo's Veto undid it."""
    pings = []
    _live_tick(world["store"], ct(2026, 9, 22, 9, 30), D1_FREE, monkeypatch, pings)
    url = _path(pings[-1][1]["actions"][0][1])
    page = world["client"].get(url)
    assert world["client"].post(_form_target(url, page.text)).status_code == 200
    real = world["store"].get(cadence.veto_key(world["state"]))
    for bad in _bad_links(world, "veto").values():
        assert world["client"].post(bad).status_code == 403
    assert world["store"].get(cadence.veto_key(world["state"])) == real
    inst = FakeInstantly(sender=LEAD)
    res, _ = _live_tick(world["store"], ct(2026, 9, 22, 10, 0), D1_FREE, monkeypatch, inst=inst)
    assert res["action"] == "vetoed" and inst.sent == []


def test_a_forged_send_hold_post_books_nothing(world, monkeypatch):
    links = _d6_card(world, monkeypatch)
    for bad in _bad_links(world, "approve").values():
        assert world["client"].post(bad).status_code == 403
    # a real Email only stays in force against a forged Send hold
    page = world["client"].get(links["Email only"])
    assert world["client"].post(_form_target(links["Email only"], page.text)).status_code == 200
    for bad in _bad_links(world, "approve").values():
        assert world["client"].post(bad).status_code == 403
    assert world["store"].get(cadence.approval_key(world["state"], "d6"))["decision"] == "veto"
    ghl = Recorder()
    res, _ = _live_tick(world["store"], ct(2026, 9, 28, 10, 10), D6_FREE, monkeypatch, ghl=ghl)
    assert res["action"] == "sent" and ghl.named("create_appointment") == []


# ------------------------------------------------------------ the pushes
def test_the_d1_card_action_is_a_view_that_opens_the_confirm_page(world, monkeypatch):
    pings = []
    _live_tick(world["store"], ct(2026, 9, 22, 9, 30), D1_FREE, monkeypatch, pings)
    kwargs = pings[-1][1]
    header = notify.format_actions(kwargs["actions"])
    assert header.startswith("view, Veto, %s/cadence/veto/" % BASE) and "http," not in header
    assert kwargs["click"] == kwargs["actions"][0][1]
    assert "then confirm" in pings[-1][0][1]
    page = world["client"].get(_path(kwargs["actions"][0][1]))
    assert page.status_code == 200 and ">Veto</button>" in page.text
    assert world["store"].get(cadence.veto_key(world["state"])) is None


def test_the_d6_card_actions_are_views_that_open_the_confirm_pages(world, monkeypatch):
    monkeypatch.setenv("CADENCE_D6_HOLD", "1")
    _d6_ready(world)
    pings = []
    _live_tick(world["store"], ct(2026, 9, 28, 10, 0), D6_FREE, monkeypatch, pings)
    kwargs = pings[-1][1]
    header = notify.format_actions(kwargs["actions"])
    assert header.startswith("view, Send hold, %s/cadence/approve/" % BASE)
    assert "; view, Email only, %s/cadence/veto-invite/" % BASE in header and "http," not in header
    for label, url in kwargs["actions"]:
        page = world["client"].get(_path(url))
        assert page.status_code == 200 and ">%s</button>" % label in page.text
    assert world["store"].get(cadence.approval_key(world["state"], "d6")) is None


def test_the_email_leg_carries_the_confirm_page_urls_only(world, monkeypatch):
    """The email copy of a card lists the action URLs; a safe-link scanner
    fetching them now reaches only the confirmation pages."""
    pings = []
    _live_tick(world["store"], ct(2026, 9, 22, 9, 30), D1_FREE, monkeypatch, pings)
    lines = notify._action_lines(pings[-1][1]["actions"])
    assert lines and all("/cadence/veto/" in line for line in lines)
    before = _snapshot(world["store"])
    for line in lines:
        url = re.search(r"https://\S+", line).group(0)
        assert world["client"].get(_path(url)).status_code == 200
    assert _snapshot(world["store"]) == before
