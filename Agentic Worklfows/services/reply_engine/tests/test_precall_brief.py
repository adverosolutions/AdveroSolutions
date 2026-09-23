"""Pre-call brief (Blueprint S6). Everything runs offline: the Instantly and
GHL clients are stand-ins, the store is a temp file, and conftest forces
MODE=shadow / LLM_FAKE=1 / NOTIFY=off."""
import csv
from datetime import timedelta

import pytest

from shared import settings, slots
from shared.settings import TZ
from shared.store import JsonFileStore

from services.reply_engine import draft as draft_mod
from services.reply_engine import precall

NOW = slots.to_tz(slots.parse_iso("2026-09-23T10:30:00-05:00"), TZ)
START = slots.to_tz(slots.parse_iso("2026-09-23T11:30:00-05:00"), TZ)


def appointment(**over):
    base = {
        "id": "appt-1",
        "contact_id": "contact-1",
        "start_iso": START.isoformat(),
        "email": "ilmi@shiningarmorcleaningnj.com",
        "first_name": "Ilmi",
        "company": "Shining Armor Cleaning NJ",
        "zoom_link": "https://us06web.zoom.us/j/86701305944",
        "campaign_id": settings.CAMPAIGNS["cleaning_reactivation"]["id"],
        "title": "Discovery Call - Ilmi Curovic",
    }
    base.update(over)
    return base


class FakeInstantly(object):
    """Only the two read methods precall uses, shaped like the live API."""

    def __init__(self, emails=None, lead=None):
        self.emails = emails or []
        self.lead = lead
        self.calls = []

    def list_emails(self, email_type="received", limit=100, **extra):
        self.calls.append(("emails", email_type, extra))
        want = "in" if email_type == "received" else "out"
        return {"items": [e for e in self.emails if e["_dir"] == want]}

    def list_leads(self, contacts=None, limit=100, **extra):
        self.calls.append(("leads", tuple(contacts or ()), extra))
        return {"items": [self.lead] if self.lead else []}


def email_row(direction, when, text, sender=None, eaccount="lorenzo@adveromedia.com"):
    sender = sender or (eaccount if direction == "out" else "info@shiningarmorcleaningnj.com")
    return {
        "_dir": direction,
        "id": "e-%s" % when,
        "timestamp_created": when,
        "subject": "Re: Ilmi, question",
        "from_address_email": sender,
        "eaccount": eaccount,
        "body": {"text": text},
        "campaign_id": settings.CAMPAIGNS["cleaning_reactivation"]["id"],
    }


THREAD = [
    email_row("out", "2026-09-18T11:17:52.000Z", "Hey Ilmi, saw that you do commercial cleaning."),
    email_row("in", "2026-09-18T15:08:27.000Z",
              "Hey Lorenzo- right know i don’t have any accounts that i will like them back because i "
              "didn’t loose any of them. If you think you can help on convincing prospect accounts that we "
              "sent the proposals and never had back from them, yes i’m open for discussion."),
    email_row("in", "2026-09-21T19:00:48.000Z", "Hi Lorenzo, please reschedule for this Wednesday around 11:30 am"),
]
LEAD = {
    "email": "ilmi@shiningarmorcleaningnj.com",
    "company_domain": "shiningarmorcleaningnj.com",
    "personalization": "Hey Ilmi, saw that you do commercial cleaning for offices and retail.",
    "email_reply_count": 3,
    "timestamp_created": "2026-09-15T14:59:32.741Z",
    "last_contacted_from": "lorenzo@adveromedia.com",
    "payload": {"companyName": "Shiningarmorcleaningnj", "website": ""},
}


# ------------------------------------------------------------------ offers
@pytest.mark.parametrize("niche,offer,expected", [
    ("cleaning", "reactivation", "cleaning_reactivation"),
    ("cleaning", "outbound", "cleaning_trigger"),
    ("bookkeeping", "reactivation", "bookkeeping_reactivation"),
    ("bookkeeping", "outbound", "bookkeeping_trigger"),
    ("recruiting", "reactivation", "recruiting_reactivation"),
    ("recruiting", "outbound", "recruiting_outbound"),
    ("generic", None, draft_mod.GENERIC_KEY),
])
def test_offer_key_matches_the_offer_sheet(niche, offer, expected):
    assert precall.offer_key(niche, offer) == expected


def test_offer_block_carries_this_offer_and_only_this_offer():
    for key in draft_mod.PRICING:
        block = precall.offer_block(key)
        assert block["mechanism"] and block["pricing_answer"] and block["minimum"]
        # the proof and guarantee must be the ones offers.md assigns to this key
        assert not draft_mod.wrong_offer_proof_problems(block["proof"], key)
        assert not draft_mod.wrong_offer_guarantee_problems(block["pricing_answer"], key)


def test_the_pricing_answer_never_quotes_a_to_confirm_figure():
    unconfirmed = set(precall.unquotable_figures())
    assert unconfirmed, "offers.md still marks the retainer TO CONFIRM; this test guards that"
    for key in draft_mod.PRICING:
        said = precall.offer_block(key)["pricing_answer"]
        assert not (set(draft_mod._norm_dollars(said)) & unconfirmed), key  # noqa: SLF001


def test_the_do_not_say_list_names_every_unquotable_figure():
    brief = precall.build_brief(appointment(), NOW, instantly=None, read_thread=False)
    text = precall.markdown(brief)
    for figure in precall.unquotable_figures():
        assert "$%s" % figure in text or figure in text.replace(",", "")


def test_everything_outside_the_do_not_say_block_is_safe_to_read_aloud():
    """The do-not-say block names the forbidden retainer figures on purpose.
    Every other line of the brief is something Lorenzo could say to the
    prospect, so it has to pass the same cross-offer checks a cold reply does."""
    brief = precall.build_brief(appointment(), NOW, instantly=None, read_thread=False)
    safe = precall.quotable_text(brief)
    assert not draft_mod.wrong_offer_proof_problems(safe, "cleaning_reactivation")
    assert not draft_mod.wrong_offer_guarantee_problems(safe, "cleaning_reactivation")
    unconfirmed = set(precall.unquotable_figures())
    assert not (set(draft_mod._norm_dollars(safe)) & unconfirmed)  # noqa: SLF001
    # ...and they really are still named, once, where they belong
    block = precall.markdown(brief)[precall.markdown(brief).index(precall.DO_NOT_SAY_HEADING):]
    assert set(draft_mod._norm_dollars(block)) >= unconfirmed  # noqa: SLF001


# -------------------------------------------------------------------- due
@pytest.mark.parametrize("minutes_before,expected", [(61, False), (60, True), (5, True), (0, False), (-1, False)])
def test_due_is_the_sixty_minutes_before_the_call(minutes_before, expected):
    now = START - timedelta(minutes=minutes_before)
    assert precall.due(appointment(), now) is expected


def test_a_cancelled_or_unreadable_booking_is_never_due():
    assert precall.due(appointment(cancelled=True), NOW) is False
    assert precall.due(appointment(ghl_status="cancelled"), NOW) is False
    assert precall.due({"id": "x", "start_iso": "not a date"}, NOW) is False
    assert precall.due({"id": "x"}, NOW) is False


# ----------------------------------------------------------------- thread
def test_direction_comes_from_the_inbox_that_owns_the_row():
    out = precall.normalise_message(THREAD[0])
    incoming = precall.normalise_message(THREAD[1])
    assert (out.direction, incoming.direction) == ("out", "in")
    assert "commercial cleaning" in out.text


def test_a_bottom_posted_reply_still_shows_its_text():
    """slots.strip_quoted returns '' when nothing survives above the quote.
    For a brief the raw body beats a blank line; nothing here feeds the time
    parser, which is where that fallback would be unsafe."""
    row = email_row("in", "2026-09-21T19:00:48.000Z",
                    "> Would Tue 2:00 or Thu 3:30 CT work?\n\nOn Sep 21, Lorenzo wrote:\n> anything")
    assert precall.normalise_message(row).text.strip()


def test_the_thread_is_read_from_both_directions_and_sorted():
    thread, error = precall.fetch_thread(FakeInstantly(THREAD), "ilmi@shiningarmorcleaningnj.com")
    assert error is None
    assert [m.direction for m in thread] == ["out", "in", "in"]
    assert thread[0].when_iso < thread[-1].when_iso


def test_a_thread_read_failure_is_reported_not_swallowed():
    class Broken(FakeInstantly):
        def list_emails(self, **kwargs):
            raise RuntimeError("HTTP 500")

    thread, error = precall.fetch_thread(Broken(), "x@y.com")
    assert thread == [] and "HTTP 500" in error
    brief = precall.build_brief(appointment(), NOW, instantly=Broken())
    assert any("thread could not be read" in p for p in brief.problems)


# ------------------------------------------------------------- objections
def test_objections_are_ranked_by_what_the_lead_actually_wrote():
    thread, _ = precall.fetch_thread(FakeInstantly(THREAD), "ilmi@shiningarmorcleaningnj.com")
    ranked = precall.rank_objections(thread, "cleaning_reactivation")
    ids = [r["id"] for r in ranked]
    assert "nothing_to_reactivate" in ids
    assert ids.index("nothing_to_reactivate") < ids.index("how_does_it_work")
    hit = next(r for r in ranked if r["id"] == "nothing_to_reactivate")
    assert hit["why"].startswith("they wrote")
    assert hit["respond"], "the response copy must come from prompts/precall_objections.md"
    assert ids[-1] == "framework"


def test_curly_apostrophes_do_not_hide_an_objection():
    """Real replies use U+2019. A pattern written with a straight apostrophe
    missed 'i don't have any accounts' on the live booking."""
    straight = precall.Message("2026-09-18T15:08:27-05:00", "in", "a@b.c", "s", "i don't have any accounts")
    curly = precall.Message("2026-09-18T15:08:27-05:00", "in", "a@b.c", "s", "i don’t have any accounts")
    for message in (straight, curly):
        ids = [r["id"] for r in precall.rank_objections([message], "cleaning_reactivation")]
        assert "nothing_to_reactivate" in ids


def test_our_own_words_never_raise_an_objection():
    ours = precall.Message("2026-09-18T15:08:27-05:00", "out", "lorenzo@adveromedia.com", "s",
                           "Happy to talk about price and send a case study")
    ids = [r["id"] for r in precall.rank_objections([ours], "cleaning_reactivation")]
    assert set(ids) == set(precall.DEFAULT_OBJECTIONS) | {"framework"}


def test_every_objection_id_has_copy_behind_it():
    blocks = precall.load_objection_blocks()
    for oid, _pattern in precall.OBJECTION_PATTERNS:
        assert blocks.get(oid), oid
    for oid in precall.DEFAULT_OBJECTIONS:
        assert blocks.get(oid), oid


# ------------------------------------------------------------------ facts
def test_local_facts_are_found_by_email_and_by_domain(tmp_path):
    path = tmp_path / "facts.csv"
    with open(str(path), "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["email", "company_domain", "company_name", "city", "state",
                                                "job_title", "company_size"])
        writer.writeheader()
        writer.writerow({"email": "ilmi@shiningarmorcleaningnj.com", "company_domain": "shiningarmorcleaningnj.com",
                         "company_name": "Shiningarmorcleaningnj Llc", "city": "Rahway", "state": "New Jersey",
                         "job_title": "Owner", "company_size": "1"})
    precall._FACTS_CACHE.clear()  # noqa: SLF001
    assert precall.local_facts("ILMI@shiningarmorcleaningnj.com", path=str(path))["city"] == "Rahway"
    assert precall.local_facts("someone-else@shiningarmorcleaningnj.com", path=str(path))["job_title"] == "Owner"
    assert precall.local_facts("nobody@example.com", path=str(path)) is None


def test_a_missing_facts_file_is_not_an_error(tmp_path):
    assert precall.local_facts("a@b.c", path=str(tmp_path / "nope.csv")) is None


def test_every_fact_carries_a_source_and_nothing_empty_is_printed():
    facts = precall.company_facts(appointment(), {"company_name": "Shiningarmorcleaningnj Llc", "city": "Rahway",
                                                  "company_website": "", "job_title": "Owner"}, LEAD)
    assert facts
    for fact in facts:
        assert fact.source and fact.value.strip()
    assert not any(f.label == "Website" and not f.value for f in facts)


def test_a_brief_with_no_facts_at_all_still_renders():
    brief = precall.build_brief({"id": "a", "start_iso": START.isoformat()}, NOW, instantly=None, read_thread=False)
    text = precall.markdown(brief)
    assert "Nothing on file" in text
    assert "Reviews and Maps footprint: not pulled" in text


# --------------------------------------------------------------- assembly
def test_the_campaign_beats_a_guess_from_the_company_name():
    """A bookkeeping prospect booked through a cleaning campaign must be
    briefed on the offer she was actually sold."""
    appt = appointment(company="Taxfo Accounting", email="sopio@taxfoaccounting.com",
                       campaign_id=settings.CAMPAIGNS["bookkeeping_reactivation"]["id"])
    brief = precall.build_brief(appt, NOW, instantly=None, read_thread=False)
    assert brief.campaign_key == "bookkeeping_reactivation"
    assert brief.niche == "bookkeeping"


def test_an_unknown_niche_is_flagged_rather_than_quietly_defaulted():
    brief = precall.build_brief({"id": "a", "start_iso": START.isoformat(), "company": "Zeta Holdings"},
                                NOW, instantly=None, read_thread=False)
    assert brief.campaign_key == draft_mod.GENERIC_KEY
    assert any("niche could not be determined" in p for p in brief.problems)


def test_the_full_brief_has_every_section_s6_asks_for():
    brief = precall.build_brief(appointment(), NOW, instantly=FakeInstantly(THREAD, LEAD))
    text = precall.markdown(brief)
    for heading in ("## Company facts", "## The thread", "## The offer for this call", "## Do not say",
                    "## Likely objections", "One-call close"):
        assert heading in text, heading
    assert "Zoom" in text or brief.zoom_link in text
    assert "<!--" not in text, "the editor note in the content file must not reach the brief"
    assert brief.meta["thread_messages"] == 3


def test_the_card_is_short_and_names_the_price_answer():
    brief = precall.build_brief(appointment(), NOW, instantly=FakeInstantly(THREAD, LEAD))
    card = precall.card_text(brief)
    assert len(card) < 1200
    assert "Offer: cleaning_reactivation" in card
    assert "20 to 30 percent" in card


# --------------------------------------------------------------- delivery
class FakeGHL(object):
    has_token = False

    def __init__(self):
        self.notes = []

    def create_note(self, contact_id, body):
        self.notes.append((contact_id, body))
        return {"shadow": True, "system": "ghl", "action": "create_note"}


def test_a_brief_is_delivered_exactly_once(tmp_path):
    store = JsonFileStore(str(tmp_path / "store.json"))
    ghl = FakeGHL()
    pushed = []
    brief = precall.build_brief(appointment(), NOW, instantly=FakeInstantly(THREAD, LEAD))
    first = precall.deliver(brief, store, ghl=ghl, now=NOW,
                            notify_fn=lambda *a, **k: pushed.append((a, k)) or {"sent": False, "test": True})
    second = precall.deliver(brief, store, ghl=ghl, now=NOW, notify_fn=lambda *a, **k: pushed.append(a))
    assert first["claimed"] is True and second.get("skipped") == "already_briefed"
    assert len(pushed) == 1
    assert len(ghl.notes) == 1 and ghl.notes[0][0] == "contact-1"
    assert "Pre-call brief" in ghl.notes[0][1]
    assert first["file"] and open(first["file"], encoding="utf-8").read().startswith("# Pre-call brief")


def test_a_reschedule_earns_a_second_brief(tmp_path):
    store = JsonFileStore(str(tmp_path / "store.json"))
    brief = precall.build_brief(appointment(), NOW, instantly=None, read_thread=False)
    precall.deliver(brief, store, now=NOW, notify_fn=lambda *a, **k: None, write=False)
    moved = precall.build_brief(appointment(start_iso=(START + timedelta(days=1)).isoformat()),
                                NOW, instantly=None, read_thread=False)
    assert moved.key != brief.key
    assert precall.deliver(moved, store, now=NOW, notify_fn=lambda *a, **k: None, write=False)["claimed"] is True


def test_the_push_failing_never_loses_the_note(tmp_path):
    store = JsonFileStore(str(tmp_path / "store.json"))
    ghl = FakeGHL()

    def boom(*a, **k):
        raise RuntimeError("ntfy down")

    brief = precall.build_brief(appointment(), NOW, instantly=None, read_thread=False)
    res = precall.deliver(brief, store, ghl=ghl, now=NOW, notify_fn=boom, write=False)
    assert res["notified"]["error"]
    assert len(ghl.notes) == 1


# ------------------------------------------------------------ manual calls
def test_manual_calendar_calls_are_briefed_even_though_show_rate_skips_them():
    """jobs/appointments_tick keeps these out of S4 because it would email the
    prospect. A brief is internal, and today both live calls are of this kind."""
    now = slots.to_tz(slots.parse_iso("2026-09-22T09:00:00-05:00"), TZ)
    calls = precall.manual_calls(now)
    assert calls, "config/ids.json google_calendar.booked_this_week is the source"
    for call in calls:
        assert call["start_iso"] and call["email"]
        assert call["source"].startswith("google_calendar")
    ilmi = [c for c in calls if "shiningarmor" in (c["email"] or "")]
    if ilmi:
        assert ilmi[0]["contact_id"], "the GHL contact id comes from ids.json opportunities_observed"


# --------------------------------------------- the review findings (A11 fixes)
@pytest.mark.parametrize("key", sorted(draft_mod.PRICING))
def test_everything_outside_the_do_not_say_block_is_safe_for_every_offer(key):
    """The invariant above, for all six keys rather than only the cleaning one.

    cleaning_trigger printed the offers.md guarantee cell verbatim, and that
    cell carries the $2,500-5,000/mo retainer marked TO CONFIRM, under the
    heading Lorenzo is most likely to read out loud."""
    niche, _, kind = key.partition("_")
    offer = "reactivation" if kind == "reactivation" else "outbound"
    brief = precall.build_brief(appointment(campaign_id=None, campaign_key=key, niche=niche, offer=offer),
                                NOW, instantly=None, read_thread=False)
    assert brief.campaign_key == key
    safe = precall.quotable_text(brief)
    unconfirmed = set(precall.unquotable_figures())
    assert not (set(draft_mod._norm_dollars(safe)) & unconfirmed), key  # noqa: SLF001
    assert not draft_mod.wrong_offer_proof_problems(safe, key), key
    assert not draft_mod.wrong_offer_guarantee_problems(safe, key), key


def test_the_guarantee_cell_keeps_its_guarantee_and_loses_only_the_to_confirm_figure():
    block = precall.offer_block("cleaning_trigger")
    assert "24,000" in block["guarantee_cell"], "the guarantee itself is quotable and must survive"
    assert "2,500" in block["guarantee_cell_raw"], "the raw cell is kept for reference"
    assert precall.UNQUOTABLE_PLACEHOLDER in block["guarantee_cell"]
    assert not (set(draft_mod._norm_dollars(block["guarantee_cell"]))
                & set(precall.unquotable_figures()))


@pytest.mark.parametrize("phrasing", [
    "Hello Lorenzo, What is your percentage? Thank you",
    "What is your percentage?",
    "How much do you charge?",
    "What does this cost?",
    "Can you send me your pricing?",
    "what's the price",
])
def test_a_direct_price_question_is_ranked_as_a_price_objection(phrasing):
    """Sopio's live thread asked exactly this and matched nothing: too_expensive
    needs the word 'expensive', cant_afford needs 'afford' or 'budget'."""
    message = precall.Message("2026-09-21T09:42:00-05:00", "in", "a@b.c", "s", phrasing)
    ranked = precall.rank_objections([message], "bookkeeping_reactivation")
    ids = [r["id"] for r in ranked]
    assert ids[0] == "price_question", ids
    hit = ranked[0]
    assert hit["why"].startswith("they wrote")
    assert hit["respond"], "the copy must come from prompts/precall_objections.md"


def test_the_most_specific_objection_leads_when_two_patterns_match_one_sentence():
    """Ilmi's sentence matches data_or_list and nothing_to_reactivate. Tuple
    declaration order put the wrong read of it first, and both blocks quoted the
    same sentence."""
    ilmi = precall.Message(
        "2026-09-18T15:08:27-05:00", "in", "info@shiningarmorcleaningnj.com", "s",
        "right know i don’t have any accounts that i will like them back because i didn’t loose any of them")
    ranked = precall.rank_objections([ilmi], "cleaning_reactivation")
    ids = [r["id"] for r in ranked]
    assert ids[0] == "nothing_to_reactivate", ids
    assert "data_or_list" not in ids, "the broader pattern owned the same sentence and must be suppressed"
    quotes = [r["why"] for r in ranked if r["why"].startswith("they wrote")]
    assert len(quotes) == len(set(quotes)), "one sentence must never produce two blocks"


def test_thread_stamps_disambiguate_morning_from_afternoon():
    morning = precall._stamp("2026-09-21T06:17:00-05:00")   # noqa: SLF001
    evening = precall._stamp("2026-09-21T18:17:00-05:00")   # noqa: SLF001
    assert morning != evening
    assert morning.endswith("am CT") and evening.endswith("pm CT")
    assert precall._stamp("2026-09-21T00:35:00-05:00") != precall._stamp("2026-09-21T12:35:00-05:00")  # noqa: SLF001
    assert precall._stamp("2026-09-21T02:00:00-05:00") == "Sep 21, 2:00am CT"  # noqa: SLF001


def test_an_unaccepted_manual_invite_is_flagged_and_a_declined_one_is_not_briefed():
    pending = appointment(response_status="needsAction")
    brief = precall.build_brief(pending, NOW, instantly=None, read_thread=False)
    assert any("has not been accepted" in p for p in brief.problems)
    assert precall.due(pending, NOW) is True, "an unaccepted invite is still briefed, with the warning"
    assert precall.due(appointment(response_status="declined"), NOW) is False
    assert precall.due(appointment(response_status="cancelled"), NOW) is False
    assert precall.due(appointment(response_status="accepted"), NOW) is True
    accepted = precall.build_brief(appointment(response_status="accepted"), NOW, instantly=None, read_thread=False)
    assert not any("has not been accepted" in p for p in accepted.problems)


def test_the_manual_seed_carries_the_response_status_it_holds():
    now = slots.to_tz(slots.parse_iso("2026-09-22T09:00:00-05:00"), TZ)
    calls = precall.manual_calls(now)
    assert calls
    assert any("response_status" in c for c in calls)
    statuses = [c.get("response_status") for c in calls]
    assert any(s for s in statuses), "config/ids.json records accepted / needsAction; neither may be dropped"


def test_an_offline_brief_does_not_report_a_read_failure():
    offline = precall.build_brief(appointment(), NOW, instantly=None, read_thread=False)
    assert any("thread not read on this run" in p for p in offline.problems)
    assert not any("could not be read" in p for p in offline.problems)

    class Broken(FakeInstantly):
        def list_emails(self, **kwargs):
            raise RuntimeError("HTTP 500")

    broken = precall.build_brief(appointment(), NOW, instantly=Broken())
    assert any("could not be read" in p for p in broken.problems)


def test_the_call_structure_is_filled_with_the_names_the_brief_already_knows():
    brief = precall.build_brief(appointment(), NOW, instantly=None, read_thread=False)
    text = precall.markdown(brief)
    assert "{first_name}" not in text and "{company}" not in text
    assert "Hey Ilmi, thanks for taking the time" in text
    assert "how Shining Armor Cleaning NJ gets work" in text
    # the discovery placeholders are genuinely unknown and stay visible
    assert "{value}" in text and "{count}" in text


def test_a_truncated_thread_says_how_many_are_missing():
    long_thread = [email_row("in", "2026-09-1%02dT12:00:00.000Z" % (i + 1), "message number %d about accounts" % i)
                   for i in range(precall.MAX_THREAD_MESSAGES + 8)]
    brief = precall.build_brief(appointment(), NOW, instantly=FakeInstantly(long_thread, LEAD))
    text = precall.markdown(brief)
    assert "## The thread (%d messages)" % precall.MAX_THREAD_MESSAGES in text
    assert "8 older message(s) are not shown" in text


def test_a_fact_is_labelled_with_the_source_it_actually_came_from():
    """'instantly lead' next to a value that came off the booking is the one
    thing the Company facts section promises not to do."""
    facts = precall.company_facts({"company": "Typed By A Human Cleaning"}, None, None)
    company = next(f for f in facts if f.label == "Company")
    assert company.value == "Typed By A Human Cleaning"
    assert company.source == "the booking"
    from_csv = precall.company_facts(appointment(), {"company_name": "Shiningarmorcleaningnj Llc"}, LEAD)
    assert next(f for f in from_csv if f.label == "Company").source == "list factory export"
    from_crm = precall.company_facts({"company": "Fallback Co"}, None, LEAD)
    assert next(f for f in from_crm if f.label == "Company").source == "instantly lead"


# --------------------------------------------------------------- the push
def test_the_card_withholds_the_company_and_their_words_on_an_unprotected_topic(monkeypatch):
    """ntfy.sh topics are world readable and notify.redact() strips only email
    addresses and URLs. There is no email leg in this .env to carry the rest."""
    monkeypatch.delenv("NTFY_TOKEN", raising=False)
    monkeypatch.delenv("NTFY_ALLOW_SENSITIVE", raising=False)
    brief = precall.build_brief(appointment(), NOW, instantly=FakeInstantly(THREAD, LEAD))
    assert precall.topic_is_protected() is False
    card = precall.card_text(brief)
    assert "Shining Armor" not in card
    assert "They last said" not in card
    assert "loose any of them" not in card
    assert "Ilmi" in card, "the first name alone is what makes the card actionable"
    assert "Shining Armor" not in precall.card_title(brief)
    # ...and every withheld line is still in the full brief
    full = precall.markdown(brief)
    assert "Shining Armor" in full and "loose any of them" in full


def test_the_card_carries_everything_once_the_topic_has_a_token(monkeypatch):
    monkeypatch.setenv("NTFY_TOKEN", "tk_not_a_real_token")
    brief = precall.build_brief(appointment(), NOW, instantly=FakeInstantly(THREAD, LEAD))
    assert precall.topic_is_protected() is True
    card = precall.card_text(brief)
    assert "Shining Armor Cleaning NJ" in card
    assert "They last said" in card
    assert "Shining Armor Cleaning NJ" in precall.card_title(brief)


# ------------------------------------------------------- delivery failures
def test_a_brief_nobody_received_is_not_marked_delivered(tmp_path):
    """notify() never raises: it returns {'sent': False, 'errors': [...]}. The
    claim used to be kept anyway, so the next tick skipped the brief and Lorenzo
    walked into the call with nothing."""
    store = JsonFileStore(str(tmp_path / "store.json"))
    dead = {"sent": False, "test": False, "shadow": False, "errors": ["ntfy: connection refused"]}
    brief = precall.build_brief(appointment(), NOW, instantly=None, read_thread=False)
    first = precall.deliver(brief, store, now=NOW, notify_fn=lambda *a, **k: dead, write=False)
    assert first["claimed"] is True and first["delivered"] is False
    assert first.get("claim_released") is True
    assert precall.already_briefed(store, "appt-1", START.isoformat()) is False
    pushed = []
    second = precall.deliver(brief, store, now=NOW,
                             notify_fn=lambda *a, **k: pushed.append(a) or {"sent": True}, write=False)
    assert second["claimed"] is True and second["delivered"] is True
    assert len(pushed) == 1
    assert precall.already_briefed(store, "appt-1", START.isoformat()) is True


def test_a_note_that_lands_is_enough_to_keep_the_claim(tmp_path):
    store = JsonFileStore(str(tmp_path / "store.json"))
    ghl = FakeGHL()
    dead = {"sent": False, "errors": ["ntfy: connection refused"]}
    brief = precall.build_brief(appointment(), NOW, instantly=None, read_thread=False)
    res = precall.deliver(brief, store, ghl=ghl, now=NOW, notify_fn=lambda *a, **k: dead, write=False)
    assert res["delivered"] is True and res.get("claim_released") is None
    assert len(ghl.notes) == 1


def test_the_brief_header_says_am_or_pm():
    """show_rate.fmt_when renders 15:00 as '3:00 CT'. A prospect who agreed
    'Thursday 4pm Eastern' cannot be checked against that at a glance."""
    afternoon = precall.build_brief(appointment(start_iso=slots.to_tz(
        slots.parse_iso("2026-09-24T15:00:00-05:00"), TZ).isoformat()), NOW, instantly=None, read_thread=False)
    morning = precall.build_brief(appointment(start_iso=slots.to_tz(
        slots.parse_iso("2026-09-24T03:00:00-05:00"), TZ).isoformat()), NOW, instantly=None, read_thread=False)
    assert afternoon.when_text.endswith("3:00pm CT")
    assert morning.when_text.endswith("3:00am CT")
    assert afternoon.when_text != morning.when_text
    assert "3:00pm CT" in precall.markdown(afternoon)


def test_the_brief_header_shows_the_leads_own_clock_when_it_is_known():
    import pytz

    brief = precall.build_brief(appointment(lead_tz="America/New_York"), NOW, instantly=None, read_thread=False)
    assert "11:30am CT" in brief.when_text
    assert "12:30pm" in brief.when_text
    assert pytz.timezone("America/New_York")
