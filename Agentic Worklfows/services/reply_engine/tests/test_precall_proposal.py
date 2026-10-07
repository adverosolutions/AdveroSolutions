"""Proposal generator and the SOP-009 verbal-commit path (Blueprint S7).

Offline: the LLM is faked, the store is a temp file, nothing sends.
"""
from datetime import timedelta

import pytest

from shared import llm, settings, slots
from shared.settings import TZ
from shared.store import JsonFileStore

from services.reply_engine import draft as draft_mod
from services.reply_engine import precall, proposal

NOW = slots.to_tz(slots.parse_iso("2026-09-23T12:05:00-05:00"), TZ)   # Wednesday, just after a call


def lead(**over):
    base = {
        "id": "appt-1",
        "contact_id": "contact-1",
        "start_iso": slots.to_tz(slots.parse_iso("2026-09-23T11:30:00-05:00"), TZ).isoformat(),
        "email": "ilmi@shiningarmorcleaningnj.com",
        "first_name": "Ilmi",
        "company": "Shining Armor Cleaning NJ",
        "campaign_id": settings.CAMPAIGNS["cleaning_reactivation"]["id"],
    }
    base.update(over)
    return base


def thread_inputs(*texts):
    rows = []
    for index, text in enumerate(texts):
        rows.append({"when_iso": "2026-09-1%dT15:08:27-05:00" % (index + 1), "direction": "in",
                     "sender": "info@shiningarmorcleaningnj.com", "subject": "Re: Ilmi, question", "text": text})
    return proposal.CallInputs(source="thread", thread=rows)


@pytest.fixture
def no_fakes():
    llm.clear_fakes()
    yield
    llm.clear_fakes()


# ------------------------------------------------------------ validation
def test_copy_problems_uses_the_same_rules_as_a_cold_reply():
    good = "# Proposal\n\nNothing up front.\n\nLorenzo"
    assert proposal.copy_problems(good, "cleaning_reactivation") == []
    assert "em or en dash" in proposal.copy_problems("A — b\n\nLorenzo", "cleaning_reactivation")
    assert "exclamation mark" in proposal.copy_problems("Great news!\n\nLorenzo", "cleaning_reactivation")
    assert any("bot" in p for p in proposal.copy_problems("Our bot runs it.\n\nLorenzo",
                                                          "cleaning_reactivation"))
    assert any("signature" in p for p in proposal.copy_problems("No sign off", "cleaning_reactivation"))


def test_a_to_confirm_figure_can_never_reach_a_proposal():
    text = "# Proposal\n\nThe retainer is $2,500 a month.\n\nLorenzo"
    problems = proposal.copy_problems(text, "cleaning_trigger")
    assert any("TO CONFIRM" in p for p in problems)


def test_a_figure_that_is_not_in_the_offer_sheet_is_refused():
    problems = proposal.copy_problems("# P\n\nThat is $9,400 a month.\n\nLorenzo", "cleaning_trigger")
    assert any("not in offers.md" in p for p in problems)


def test_another_offers_guarantee_is_refused():
    text = "# P\n\nI guarantee $15,000 in new annual client fees within 90 days.\n\nLorenzo"
    assert proposal.copy_problems(text, "cleaning_trigger")
    assert proposal.copy_problems(text, "bookkeeping_trigger") == []


# --------------------------------------------------------------- deposit
def test_a_commission_offer_says_there_is_no_deposit_and_flags_the_blueprint():
    text, notes = proposal.deposit_terms("cleaning_reactivation")
    assert "no deposit" in text.lower()
    assert notes and "50 percent" in notes[0]
    assert proposal.copy_problems(text + "\n\nLorenzo", "cleaning_reactivation") == []


def test_a_retainer_offer_carries_the_deposit_without_inventing_a_number():
    text, notes = proposal.deposit_terms("cleaning_trigger")
    assert "half of the setup fee" in text.lower()
    assert draft_mod._norm_dollars(text) == []  # noqa: SLF001 - no figure at all
    assert notes and "TO CONFIRM" in notes[0]


def test_only_reactivation_offers_carry_the_six_month_attribution_window():
    assert "6 months" in (proposal.attribution_line("cleaning_reactivation") or "")
    assert proposal.attribution_line("cleaning_trigger") is None


# ----------------------------------------------------------------- build
@pytest.mark.parametrize("key", sorted(draft_mod.PRICING))
def test_every_offer_produces_a_clean_proposal(key, no_fakes):
    niche, _, kind = key.partition("_")
    offer = "reactivation" if kind == "reactivation" else "outbound"
    built = proposal.build_proposal(lead(niche=niche, offer=offer, campaign_id=None, campaign_key=key),
                                    NOW, inputs=thread_inputs("We send a lot of proposals that go quiet."),
                                    use_llm=False)
    assert built.campaign_key == key
    assert built.problems == [], built.problems
    assert built.text.strip().endswith("Lorenzo")
    block = precall.offer_block(key)
    assert block["mechanism"] in built.text
    assert block["proof"] in built.text
    if key.endswith("_reactivation"):
        assert "6 months" in built.text
    else:
        assert "6 months" not in built.text


def test_the_recap_quotes_the_lead_and_never_invents_a_call():
    built = proposal.build_proposal(lead(), NOW, inputs=thread_inputs(
        "We do not lose accounts, but we send proposals that never come back."), use_llm=False)
    assert "You wrote on" in built.text
    assert "never come back" in built.text


def test_with_no_record_of_the_call_the_recap_is_a_hole_not_a_fabrication():
    built = proposal.build_proposal(lead(), NOW, inputs=proposal.CallInputs(), use_llm=False)
    assert "Nothing on file from the call" in built.text
    assert "You wrote on" not in built.text


def test_lorenzos_notes_win_over_the_thread():
    inputs = thread_inputs("Something from email")
    inputs.notes = "- 14 proposals a month go quiet\n- average job 2 thousand"
    inputs.source = "notes"
    built = proposal.build_proposal(lead(), NOW, inputs=inputs, use_llm=False)
    assert "14 proposals a month go quiet" in built.text
    assert "Something from email" not in built.text


def test_the_longest_thing_they_said_leads_the_recap():
    """Reverse chronological put 'please reschedule for Wednesday' first and
    pushed the sentence that defines the deal to the bottom, truncated. The
    reschedule line is now dropped outright as booking chatter, so the one
    sentence that defines the deal is the whole recap."""
    inputs = thread_inputs("We never lose accounts, but every proposal we send that goes unanswered is money we "
                           "already spent chasing, and nobody here follows up on them at all.",
                           "please reschedule for Wednesday")
    built = proposal.build_proposal(lead(), NOW, inputs=inputs, use_llm=False)
    body = built.text[built.text.index("## What you told me"):]
    assert "never lose accounts" in body
    assert "please reschedule" not in body


def test_a_thread_that_contradicts_the_mechanism_raises_a_check_for_lorenzo():
    built = proposal.build_proposal(lead(), NOW, inputs=thread_inputs(
        "i don’t have any accounts that i will like them back because i didn’t loose any of them"),
        use_llm=False)
    notes = built.meta["notes_for_lorenzo"]
    assert any("did not lose accounts" in n for n in notes)


def test_fireflies_is_absent_and_says_so():
    status = proposal.fireflies_status()
    assert status["available"] is False and status["reason"] == "no_fireflies_api_key"
    inputs = proposal.gather_inputs("a@b.c", instantly=None, thread=[])
    assert any("no Fireflies transcript" in w for w in inputs.warnings)


def test_a_transcript_file_is_used_when_one_is_handed_in(tmp_path):
    path = tmp_path / "call.txt"
    path.write_text("Lorenzo: how many proposals go quiet\nIlmi: about fifteen a month", encoding="utf-8")
    inputs = proposal.gather_inputs("a@b.c", transcript_path=str(path), thread=[])
    assert inputs.source == "fireflies" and "fifteen a month" in inputs.transcript


def test_an_unreadable_transcript_is_a_warning_not_a_crash(tmp_path):
    inputs = proposal.gather_inputs("a@b.c", transcript_path=str(tmp_path / "missing.txt"), thread=[])
    assert any("could not be read" in w for w in inputs.warnings)
    assert inputs.source in ("none", "thread")


# ------------------------------------------------------------------- llm
def test_a_polished_proposal_that_breaks_a_copy_rule_is_thrown_away(no_fakes):
    llm.register_fake("proposal", lambda s, u, j: "# Proposal\n\nWe use an automated system — it works.\n\nLorenzo")
    built = proposal.build_proposal(lead(), NOW, inputs=thread_inputs("hi"), use_llm=True)
    assert built.model == "template"
    assert "rejected" in built.rationale
    assert "automated" not in built.text


def test_a_polished_proposal_that_invents_a_figure_is_thrown_away(no_fakes):
    llm.register_fake("proposal", lambda s, u, j: "# Proposal\n\nIt is $7,300 a month.\n\nLorenzo")
    built = proposal.build_proposal(lead(), NOW, inputs=thread_inputs("hi"), use_llm=True)
    assert built.model == "template" and built.problems == []


def test_a_clean_polish_is_kept(no_factory_needed=None, no_fakes=None):
    llm.clear_fakes()
    llm.register_fake("proposal", lambda s, u, j: "# Proposal for Shining Armor Cleaning NJ\n\n"
                                                  "Nothing up front, and $0 if nothing closes.\n\nLorenzo")
    try:
        built = proposal.build_proposal(lead(), NOW, inputs=thread_inputs("hi"), use_llm=True)
        assert built.model == llm.model_for("proposal")
        assert built.problems == []
    finally:
        llm.clear_fakes()


def test_an_llm_failure_keeps_the_skeleton(no_fakes):
    def boom(system, user, json_mode):
        raise RuntimeError("model down")

    llm.register_fake("proposal", boom)
    built = proposal.build_proposal(lead(), NOW, inputs=thread_inputs("hi"), use_llm=True)
    assert built.model == "template" and "LLM failed" in built.rationale
    assert built.problems == []


# --------------------------------------------------- SOP-009 verbal commit
def test_the_verbal_commit_path_is_three_drafts_in_sop_order(monkeypatch):
    monkeypatch.setenv(proposal.PAYMENT_LINK_ENV, "https://pay.example.com/advero")
    built = proposal.build_proposal(lead(), NOW, inputs=thread_inputs("hi"), use_llm=False)
    drafts = proposal.verbal_commit_drafts(built, NOW)
    assert [d.key for d in drafts] == ["immediate", "day1", "day3"]
    assert all(d.sendable for d in drafts), [d.problems for d in drafts]
    assert "https://pay.example.com/advero" in drafts[0].body
    assert all(d.body.strip().endswith("Lorenzo") for d in drafts)
    assert all(d.subject and "Subject:" not in d.body for d in drafts)


def test_without_a_payment_link_the_first_draft_is_blocked_not_silently_empty(monkeypatch):
    monkeypatch.delenv(proposal.PAYMENT_LINK_ENV, raising=False)
    built = proposal.build_proposal(lead(), NOW, inputs=thread_inputs("hi"), use_llm=False)
    drafts = proposal.verbal_commit_drafts(built, NOW)
    first = drafts[0]
    assert not first.sendable
    assert "{payment_link}" in first.body
    assert any("payment link" in p for p in first.problems)


def test_the_link_goes_out_within_the_hour_and_the_nudges_land_on_business_days(monkeypatch):
    monkeypatch.setenv(proposal.PAYMENT_LINK_ENV, "https://pay.example.com/x")
    built = proposal.build_proposal(lead(), NOW, inputs=thread_inputs("hi"), use_llm=False)
    drafts = {d.key: slots.parse_iso(d.due_iso) for d in proposal.verbal_commit_drafts(built, NOW)}
    assert drafts["immediate"] - NOW <= timedelta(hours=1)
    assert drafts["day1"].date() == (NOW + timedelta(days=1)).date()
    # NOW is a Wednesday, so day 3 lands on Saturday and must roll to Monday
    assert drafts["day3"].weekday() < 5
    assert drafts["day3"] >= NOW + timedelta(days=3)
    for due in drafts.values():
        assert settings.SEND_WINDOW[0] <= due.hour < settings.SEND_WINDOW[1]


def test_an_evening_call_does_not_email_the_link_at_midnight(monkeypatch):
    monkeypatch.setenv(proposal.PAYMENT_LINK_ENV, "https://pay.example.com/x")
    late = slots.to_tz(slots.parse_iso("2026-09-23T19:40:00-05:00"), TZ)
    built = proposal.build_proposal(lead(), late, inputs=thread_inputs("hi"), use_llm=False)
    due = slots.parse_iso(proposal.verbal_commit_drafts(built, late)[0].due_iso)
    assert settings.SEND_WINDOW[0] <= due.hour < settings.SEND_WINDOW[1]
    assert due > late


# ---------------------------------------------------------------- deliver
class FakeGHL(object):
    has_token = False

    def __init__(self):
        self.notes = []

    def create_note(self, contact_id, body):
        self.notes.append((contact_id, body))
        return {"shadow": True, "system": "ghl", "action": "create_note"}


def test_a_proposal_is_filed_and_announced_exactly_once(tmp_path):
    store = JsonFileStore(str(tmp_path / "store.json"))
    ghl = FakeGHL()
    pushed = []
    built = proposal.build_proposal(lead(), NOW, inputs=thread_inputs("hi"), use_llm=False)
    verbal = proposal.verbal_commit_drafts(built, NOW)
    first = proposal.deliver(built, store=store, ghl=ghl, now=NOW, verbal=verbal,
                             notify_fn=lambda *a, **k: pushed.append(a) or {"test": True})
    second = proposal.deliver(built, store=store, ghl=ghl, now=NOW, verbal=verbal,
                              notify_fn=lambda *a, **k: pushed.append(a))
    assert first["claimed"] and second.get("skipped") == "already_drafted"
    assert len(pushed) == 1 and len(ghl.notes) == 1
    assert first["document"]["status"] == "manual"
    text = open(first["file"], encoding="utf-8").read()
    assert "DRAFT. Nothing in this file has been sent" in text
    assert "Verbal commit path (SOP-009), drafts only" in text
    assert "Draft only, not sent" in ghl.notes[0][1]


def test_a_call_with_no_telemetry_says_so_on_the_document(tmp_path):
    built = proposal.build_proposal(lead(), NOW, inputs=thread_inputs("hi"), use_llm=False,
                                    held_evidence="unknown")
    text = proposal.document(built)
    assert "No Zoom telemetry" in text
    assert "Held evidence: unknown" in text


def test_a_blocked_proposal_is_marked_blocked_on_the_document():
    built = proposal.build_proposal(lead(), NOW, inputs=thread_inputs("hi"), use_llm=False)
    built.text = "# P\n\nWe charge $2,500 a month.\n\nLorenzo"
    built.problems = proposal.copy_problems(built.text, built.campaign_key)
    assert "BLOCKED" in proposal.document(built)


# ------------------------------------- the GHL follow-up sequence copy
SPEC_PATH = (__import__("pathlib").Path(__file__).resolve().parents[3]
             / "changesets" / "ghl_workflows" / "proposal_follow_up.md")


def _spec_copy_blocks():
    """Every fenced block in the build spec that is an email body."""
    import re

    text = SPEC_PATH.read_text(encoding="utf-8")
    out = {}
    for match in re.finditer(r"(?ms)^### (.+?)\n```\n(.*?)^```", text):
        out[match.group(1).strip()] = match.group(2)
    return out


def test_the_follow_up_sequence_copy_obeys_the_same_rules_as_every_other_send():
    blocks = _spec_copy_blocks()
    assert len(blocks) == 6, sorted(blocks)
    for name, body in blocks.items():
        key = "cleaning_trigger" if "outbound" in name else "cleaning_reactivation"
        problems = proposal.copy_problems(body, campaign_key=key)
        assert problems == [], (name, problems)


def test_each_case_study_branch_uses_its_own_offer_types_proof():
    blocks = _spec_copy_blocks()
    reactivation = next(b for n, b in blocks.items() if "reactivation" in n)
    outbound = next(b for n, b in blocks.items() if "outbound" in n)
    assert precall.offer_block("cleaning_reactivation")["proof"] in reactivation
    assert precall.offer_block("cleaning_trigger")["proof"] in outbound
    assert not draft_mod.wrong_offer_proof_problems(reactivation, "cleaning_reactivation")
    assert not draft_mod.wrong_offer_proof_problems(outbound, "cleaning_trigger")


def test_the_spec_points_at_the_draft_workflow_that_already_exists():
    text = SPEC_PATH.read_text(encoding="utf-8")
    ids = settings.IDS["ghl"]
    assert ids["workflows"]["proposal_follow_up"]["id"] in text
    assert ids["pipelines"]["sales"]["stages"]["proposal_sent"]["id"] in text
    assert ids["pipelines"]["sales"]["stages"]["follow_up_later"]["id"] in text


def test_the_spec_never_restates_a_price():
    """The proposal holds the numbers. A follow-up that repeats one is how a
    figure drifts away from config/offers.md."""
    for name, body in _spec_copy_blocks().items():
        figures = set(draft_mod._norm_dollars(body))  # noqa: SLF001
        assert not (figures & set(precall.unquotable_figures())), name


# --------------------------------------------- the review findings (A11 fixes)
TAXFO_THREAD = [
    "Hello Lorenzo, What is your percentage? Thank you",
    "Hello, Thursday 4pm Eastern time. works for me 237-791-5700",
    "Hello Lorenzo. I am available every day 3pm-6pm Estern time. let me know what wirks.",
]
SHINING_THREAD = [
    "Sure Let's get together on Monday at 2 CTS that works for me . Best reagrds",
    "I have an one emergence please reschedule for this Wednesday around 11:30 am",
]


def test_scheduling_chatter_never_reaches_the_proposal_recap():
    """Taxfo's real thread produced three bullets of booking chatter, her phone
    number and her typos, in a document Lorenzo is told to paste and send."""
    built = proposal.build_proposal(lead(company="Taxfo Accounting", email="sopiosvanishvili@taxfoaccounting.com"),
                                    NOW, inputs=thread_inputs(*TAXFO_THREAD), use_llm=False)
    body = built.text[built.text.index("## What you told me"):]
    for banned in ("works for me", "reschedule", "237-791-5700", "237", "let me know what wirks"):
        assert banned not in body, banned
    assert "Nothing on file from the call" in body, "an empty hole beats three lines of booking chatter"
    shining = proposal.build_proposal(lead(), NOW, inputs=thread_inputs(*SHINING_THREAD), use_llm=False)
    shining_body = shining.text[shining.text.index("## What you told me"):]
    assert "Best reagrds" not in shining_body
    assert "please reschedule" not in shining_body


def test_a_substantive_sentence_survives_next_to_the_chatter():
    inputs = thread_inputs(SHINING_THREAD[0],
                           "We never lose accounts, but every proposal we send that goes unanswered is money "
                           "already spent chasing them.",
                           SHINING_THREAD[1])
    built = proposal.build_proposal(lead(), NOW, inputs=inputs, use_llm=False)
    body = built.text[built.text.index("## What you told me"):]
    assert "every proposal we send that goes unanswered" in body
    assert "reschedule" not in body and "works for me" not in body


def test_a_quoted_phone_number_and_sign_off_are_stripped_from_a_kept_quote():
    cleaned = proposal.clean_quote("We lose about ten accounts a year.\nCall me on 237-791-5700\nBest regards")
    assert "237" not in cleaned and "791" not in cleaned
    assert "Best regards" not in cleaned
    assert "ten accounts a year" in cleaned


def test_the_prospects_own_number_in_the_recap_does_not_block_the_proposal():
    """Their number is their sentence, not our copy. Blocking on it told Lorenzo
    the offer sheet was violated when the prospect said the figure."""
    inputs = thread_inputs("Our last agency charged us $2,500 a month for the accounts work and we got nothing "
                           "out of it at all.")
    built = proposal.build_proposal(lead(), NOW, inputs=inputs, use_llm=False)
    assert "$2,500" in built.text, "the quote is still verbatim"
    assert built.problems == [], built.problems
    assert any("their words, not our copy" in n for n in built.meta["notes_for_lorenzo"])


def test_lorenzos_own_note_about_their_numbers_does_not_block_the_proposal():
    inputs = proposal.CallInputs(source="notes")
    inputs.notes = "- average job is $2,000\n- 14 proposals a month go quiet"
    built = proposal.build_proposal(lead(), NOW, inputs=inputs, use_llm=False)
    assert "$2,000" in built.text
    assert built.problems == [], built.problems


def test_the_prospects_own_word_automated_in_a_quote_does_not_block_the_proposal():
    inputs = thread_inputs("We already tried an automated follow up tool for our accounts last year and it did "
                           "not do anything for us.")
    built = proposal.build_proposal(lead(), NOW, inputs=inputs, use_llm=False)
    assert built.problems == [], built.problems
    assert "automated" in built.text


@pytest.mark.parametrize("quote,why", [
    ("Sounds great, we lose maybe 10 accounts a year!", "exclamation mark"),
    ("Our accounts churn — about ten a year", "em or en dash"),
    ("We already tried an AI tool on our accounts", "mentions AI"),
])
def test_their_punctuation_and_vocabulary_never_block_the_proposal(quote, why):
    built = proposal.build_proposal(lead(), NOW, inputs=thread_inputs(quote), use_llm=False)
    assert built.problems == [], (why, built.problems)


def test_our_own_copy_is_still_validated_even_with_quotes_present():
    """Blanking the quotes must not blank the rest of the document."""
    inputs = thread_inputs("We lose about ten accounts a year.")
    built = proposal.build_proposal(lead(), NOW, inputs=inputs, use_llm=False)
    built.text = built.text.replace("## What I will build", "## What I will build\n\nOur bot runs it.")
    problems = proposal.copy_problems(built.text, built.campaign_key,
                                      quoted=built.meta["quoted_spans"])
    assert any("bot" in p for p in problems)


# ---------------------------------------------------------- the campaign
def test_the_proposal_resolves_the_campaign_from_the_instantly_lead(monkeypatch):
    """build_brief recovers the campaign from the lead record; this used to read
    only appointment['campaign_id'], which normalise_ghl_event never sets, so the
    brief and the proposal for one call could quote two different offers."""
    booking = {"id": "ghl-appt-1", "contact_id": "c1", "company": "Shining Armor Cleaning NJ",
               "first_name": "Ilmi", "email": "ilmi@shiningarmorcleaningnj.com",
               "start_iso": slots.to_tz(slots.parse_iso("2026-09-23T11:30:00-05:00"), TZ).isoformat()}

    class LeadOnly(object):
        def list_leads(self, contacts=None, limit=100, **extra):
            return {"items": [{"email": "ilmi@shiningarmorcleaningnj.com",
                               "campaign": settings.CAMPAIGNS["cleaning_trigger"]["id"]}]}

    brief = precall.build_brief(booking, NOW, instantly=LeadOnly(), read_thread=True)
    built = proposal.build_proposal(booking, NOW, inputs=thread_inputs("We want more accounts"),
                                    instantly=LeadOnly(), use_llm=False)
    assert brief.campaign_key == "cleaning_trigger"
    assert built.campaign_key == brief.campaign_key, "the brief and the proposal must agree about the offer"
    assert "20 to 30 percent" not in built.text, "that is the reactivation pricing, not cleaning_trigger's"
    assert "There is no deposit" not in built.text


def test_an_unmatched_niche_blocks_the_proposal_the_way_it_warns_the_brief():
    booking = {"id": "a9", "company": "Northstar Group", "first_name": "Dana",
               "start_iso": slots.to_tz(slots.parse_iso("2026-09-23T11:30:00-05:00"), TZ).isoformat()}
    brief = precall.build_brief(booking, NOW, instantly=None, read_thread=False)
    built = proposal.build_proposal(booking, NOW, inputs=thread_inputs("hello"), use_llm=False)
    assert any("niche could not be determined" in p for p in brief.problems)
    assert any("niche could not be determined" in p for p in built.problems), built.problems
    assert built.sendable is False
    assert "BLOCKED" in proposal.document(built)


# ------------------------------------------------------- the claim and date
def test_the_claim_and_the_prepared_date_come_from_the_call_not_the_clock():
    late = {"id": "appt-late", "company": "Metro Clean", "first_name": "Ray", "contact_id": "c1",
            "campaign_id": settings.CAMPAIGNS["cleaning_reactivation"]["id"],
            "start_iso": slots.to_tz(slots.parse_iso("2026-09-24T23:00:00-05:00"), TZ).isoformat()}
    before = slots.to_tz(slots.parse_iso("2026-09-24T23:25:00-05:00"), TZ)
    after = slots.to_tz(slots.parse_iso("2026-09-25T00:05:00-05:00"), TZ)
    first = proposal.build_proposal(late, before, inputs=thread_inputs("hi"), use_llm=False)
    second = proposal.build_proposal(late, after, inputs=thread_inputs("hi"), use_llm=False)
    assert first.call_date == second.call_date == "2026-09-24"
    assert first.key == second.key == "proposal:appt-late:2026-09-24"
    assert "September 24, 2026" in first.text and "September 24, 2026" in second.text


def test_already_drafted_answers_before_anything_is_built(tmp_path):
    store = JsonFileStore(str(tmp_path / "store.json"))
    appointment = lead()
    call_date = proposal.call_date_for(appointment, NOW)
    assert proposal.already_drafted(store, appointment["id"], call_date) is False
    built = proposal.build_proposal(appointment, NOW, inputs=thread_inputs("hi"), use_llm=False)
    proposal.deliver(built, store=store, now=NOW, notify_fn=lambda *a, **k: {"test": True}, write=False)
    assert proposal.already_drafted(store, appointment["id"], call_date) is True
    assert proposal.already_drafted(None, appointment["id"], call_date) is False


def test_two_proposals_on_one_day_for_one_company_do_not_overwrite_each_other(tmp_path):
    """The filename had no discriminator, so two calls that slug the same wrote
    one file while the digest reported both as filed."""
    first = proposal.build_proposal(lead(id="appt-1"), NOW, inputs=thread_inputs("hi"), use_llm=False)
    second = proposal.build_proposal(lead(id="appt-2"), NOW, inputs=thread_inputs("hi"), use_llm=False)
    a = proposal.write_draft(first, directory=tmp_path)
    b = proposal.write_draft(second, directory=tmp_path)
    assert a != b
    assert len(list(tmp_path.glob("*.md"))) == 2
    assert "appt1" in a and "appt2" in b


def test_a_forced_transcript_proposal_replaces_the_one_the_tick_already_took(tmp_path):
    """The runbook's own --proposal-for --transcript command was swallowed by
    the claim the 5-minute tick had already taken that day."""
    store = JsonFileStore(str(tmp_path / "store.json"))
    pushed = []
    scheduled = proposal.build_proposal(lead(), NOW, inputs=thread_inputs("hi"), use_llm=False)
    first = proposal.deliver(scheduled, store=store, now=NOW,
                             notify_fn=lambda *a, **k: pushed.append(a) or {"test": True})
    assert first["claimed"] and first["file"]
    better = proposal.build_proposal(lead(), NOW, use_llm=False, inputs=proposal.CallInputs(
        source="fireflies", transcript="Lorenzo: how many go quiet\nIlmi: about fifteen a month"))
    forced = proposal.deliver(better, store=store, now=NOW, replace=True,
                              notify_fn=lambda *a, **k: pushed.append(a) or {"test": True})
    assert forced["claimed"] is True and forced["replaced"] is True
    assert forced.get("skipped") is None
    assert forced["file"] and forced["file"] != first["file"], "both documents survive on disk"
    assert "forced" in forced["file"]
    assert len(pushed) == 2
    # without replace the claim still protects the scheduled pass
    again = proposal.deliver(better, store=store, now=NOW, notify_fn=lambda *a, **k: pushed.append(a))
    assert again.get("skipped") == "already_drafted" and len(pushed) == 2


# ------------------------------------------------------------- the document
def test_the_client_facing_body_is_delimited_from_the_review_header():
    built = proposal.build_proposal(lead(), NOW, inputs=thread_inputs("hi"), use_llm=False,
                                    held_evidence="unknown")
    verbal = proposal.verbal_commit_drafts(built, NOW)
    text = proposal.document(built, verbal)
    assert proposal.INTERNAL_BANNER in text
    assert proposal.CLIENT_BANNER in text
    assert text.index(proposal.INTERNAL_BANNER) < text.index(proposal.CLIENT_BANNER)
    assert text.index(proposal.CLIENT_BANNER) < text.index("# Proposal for")
    body = proposal.client_body(text)
    assert body.startswith("# Proposal for")
    assert "No Zoom telemetry" not in body
    assert "Check:" not in body
    assert "Verbal commit path" not in body, "the SOP-009 drafts are internal too"
    assert body.strip().endswith("Lorenzo")


def test_the_stamp_on_a_verbal_commit_due_time_says_am_or_pm():
    built = proposal.build_proposal(lead(), NOW, inputs=thread_inputs("hi"), use_llm=False)
    text = proposal.document(built, proposal.verbal_commit_drafts(built, NOW))
    stamps = [line for line in text.splitlines() if line.startswith("## ") and ", due " in line]
    assert stamps
    for line in stamps:
        assert line.rstrip().endswith("am CT") or line.rstrip().endswith("pm CT"), line


def test_the_case_study_branch_has_no_untagged_default():
    """'No tag' and 'tagged reactivation' used to collapse into one branch, so a
    trigger prospect whose tag did not apply got the reactivation proof line."""
    import json as _json
    import re as _re

    text = SPEC_PATH.read_text(encoding="utf-8")
    block = _re.search(r"(?ms)^```json\n(.*?)^```", text)
    assert block, "the spec must carry a JSON representation"
    spec = _json.loads(block.group(1))
    branch = next(s for s in spec["steps"]
                  if s.get("type") == "if_else"
                  and "offer-outbound" in _json.dumps(s))
    conditions = _json.dumps(branch.get("branches") or [])
    assert "offer-outbound" in conditions and "offer-reactivation" in conditions
    untagged = branch.get("else") or []
    assert untagged, "the untagged path must exist and do something"
    assert not any(step.get("type") == "send_email" for step in untagged), untagged
    assert any(step.get("type") == "add_task" for step in untagged)
    assert "yes" not in branch and "no" not in branch, "the two-way shape is what caused the bug"


def test_a_sign_off_in_the_middle_of_a_line_still_ends_the_quote():
    """The live cleaning thread ends '... works for me . Best reagrds ; Ilmi
    Curovic ShinigArmorCleaningNJ, LLC' on one line, and the company name inside
    that signature was enough to make the chatter filter keep the message."""
    chatter = ("Sure Let’s get together on Monday at 2 CTS that works for me . "
               "Best reagrds ; Ilmi Curovic ShinigArmorCleaningNJ, LLC")
    cleaned = proposal.clean_quote(chatter)
    assert "Best reagrds" not in cleaned and "Ilmi Curovic" not in cleaned
    assert proposal.is_scheduling_chatter(cleaned) is True
    real = ("Hey Lorenzo- thank you for you’re email , right know i don’t have any accounts that i will "
            "like them back because i didn’t loose any of them. If you think you can help on convincing "
            "prospect accounts that we sent the proposals and never had back from them , yes i’m open for "
            "discussion. Best regards; Ilmi Curovic ShiningArmorClenaingNJ, LLC")
    kept = proposal.clean_quote(real)
    assert "Best regards" not in kept and "ShiningArmorClenaingNJ" not in kept
    assert "thank you for you" in kept, "a mid-sentence 'thank you' must never truncate the message"
    assert "open for discussion" in kept
    assert proposal.is_scheduling_chatter(kept) is False


def test_the_whole_live_thread_produces_one_recap_bullet():
    """Both live threads, end to end: the deal sentence survives, every piece of
    booking chatter goes."""
    built = proposal.build_proposal(lead(), NOW, use_llm=False, inputs=thread_inputs(
        "Hey Lorenzo- thank you for you’re email , right know i don’t have any accounts that i will like "
        "them back because i didn’t loose any of them. If you think you can help on convincing prospect "
        "accounts that we sent the proposals and never had back from them , yes i’m open for discussion. "
        "Best regards; Ilmi Curovic ShiningArmorClenaingNJ, LLC",
        "Sure Let’s get together on Monday at 2 CTS that works for me . Best reagrds ; Ilmi Curovic",
        "Hi Lorenzo, I have an one emergence please reschedule for this Wednesday around 11:30 am"))
    body = built.text[built.text.index("## What you told me"):built.text.index("## What I will build")]
    assert body.count("- You wrote on") == 1, body
    assert "open for discussion" in body
    for banned in ("reschedule", "works for me", "Best reagrds", "Ilmi Curovic"):
        assert banned not in body, banned


def test_the_proposal_card_withholds_the_company_on_an_unprotected_topic(monkeypatch, tmp_path):
    monkeypatch.delenv("NTFY_TOKEN", raising=False)
    monkeypatch.delenv("NTFY_ALLOW_SENSITIVE", raising=False)
    built = proposal.build_proposal(lead(), NOW, inputs=thread_inputs("We lose ten accounts a year"),
                                    use_llm=False)
    card = proposal.card_text(built)
    assert "Shining Armor" not in card
    assert "Shining Armor" not in proposal.card_title(built)
    assert "cleaning_reactivation" in card
    monkeypatch.setenv("NTFY_TOKEN", "tk_not_real")
    assert "Shining Armor Cleaning NJ" in proposal.card_text(built)
    assert "Shining Armor Cleaning NJ" in proposal.card_title(built)
    # the full company name is still in the document and the file
    assert "Shining Armor Cleaning NJ" in proposal.document(built)
