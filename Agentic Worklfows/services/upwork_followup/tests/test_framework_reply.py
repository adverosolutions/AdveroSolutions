"""The setter-framework reply (Lorenzo, 2026-10-05), its price band (Lorenzo,
2026-10-06: $500 to $3,500 by default, never below $500), routing by the
reply classifier's label, the copy gate's framework checks, and the weekend
watch. Every model call is an injected fake; nothing here spends a token.
Invented clients and invented assessment lines only (shapes taken from real
assessments)."""
from datetime import datetime, timezone

import pytest

from services.upwork_followup import collect, copy_gate, draft, sequence, watch
from services.upwork_followup.tests import test_watch as tw

TUESDAY = datetime(2026, 10, 6, 15, 0, tzinfo=timezone.utc)     # Tuesday 10:00 CT
FRIDAY = datetime(2026, 10, 9, 20, 0, tzinfo=timezone.utc)      # Friday 15:00 CT
SATURDAY = datetime(2026, 10, 10, 17, 0, tzinfo=timezone.utc)   # Saturday 12:00 CT

NOTES = ("Time:\n- 4 to 8 hours, 1 to 2 calendar weeks.\n\n"
         "Standard pricing:\n- Market for this intake: $1,000 to $2,500 fixed.\n"
         "- Recurring software: HubSpot Starter about $20 a month.")

NAMED = "Would $750 work for the showroom intake? How long would it take?"


class FakeLLM(object):
    def __init__(self, *outputs):
        self.outputs = list(outputs)
        self.calls = []

    def __call__(self, role, system, user, max_tokens=800, json_mode=False):
        self.calls.append({"system": system, "user": user})
        return self.outputs.pop(0)


@pytest.fixture(autouse=True)
def no_real_llm(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("shared.llm.complete must not be called in these tests")
    monkeypatch.setattr(draft.shared_llm, "complete", boom)


def room(client_text="Thanks for the video. How much would the showroom intake cost, and how long would it take?",
         notes=NOTES, budget=750, location="Client in Virginia, US (America/New_York)."):
    return {
        "room_id": "room_fw1", "client": "Brightline Tile", "client_first_name": None,
        "room_type": "ONE_ON_ONE", "job_title": "HubSpot intake for tile showroom quotes",
        "messages": [
            {"id": "m1", "side": "freelancer", "at": "2026-10-05T15:00:00Z", "text": "Here's the Loom."},
            {"id": "m2", "side": "client", "at": "2026-10-06T14:00:00Z", "text": client_text},
        ],
        "last_side": "client",
        "job": {"post": "Brightline Tile wants showroom quote requests from the website form in HubSpot.",
                "proposal": "I built a HubSpot intake flow for your showroom quote requests.", "beats": [],
                "ask_before_quoting": ["Which HubSpot tier are you on?"], "private_notes": notes,
                "loom_url": None, "applied_at": None, "client_location": location, "budget": budget},
    }


def labelled(*entries):
    """A thread whose history holds the classifier labels sequence.py records,
    one (message_id, label) or (message_id, label, event) per entry."""
    history = []
    for entry in entries:
        event = entry[2] if len(entry) > 2 else "client_reply"
        history.append({"at": "2026-10-06T14:05:00Z", "event": event, "message_id": entry[0], "label": entry[1]})
    return {"history": history}


QUESTION = labelled(("m2", "question"))

REPLY = ("Thanks for getting back to me. For the showroom quote intake I'd put it between $750 and $3,500, and "
         "I aim to finish in about 2 weeks, faster if I clear my schedule for it. The range isn't complete yet: "
         "I need your HubSpot tier and how many website forms feed it. On a brief Upwork call you'd leave with "
         "the scope, I'd walk you through how the setup works, and it's a free consult on anything related. I'm "
         "free now, in the next couple of hours, or tomorrow at 1pm ET (noon CT).\n"
         "NEEDS_YOU:\n- none\nPROPOSES_CALL: yes")


def gate(body, r=None, band=(750, 3500), framework=False):
    return copy_gate.check(body, "reply", r or room(), draft.load_offers(), [NOTES], band=band, framework=framework)


# ---------------------------------------------------------------- the band
@pytest.mark.parametrize("budget,top,band", [
    (None, None, (500, 3500)),       # no budget, no assessment: the default
    (750, None, (750, 3500)),        # $750 budget, no assessment
    (300, None, (500, 3500)),        # never below $500
    (1977, None, (1900, 3500)),      # rounded down to a clean number
    (5000, 6000, (5000, 6000)),      # the assessment raised the top
    (3500, None, None),              # the budget reaches the top: no range
    (3450, None, None),              # $3,400 to $3,500 is one clean step: no range
    (3400, None, None),
    (3350, None, (3300, 3500)),      # two steps wide is a range
    (3500, 3600, None),              # $3,500 to $3,600: one step, no range
    (None, 3550, (500, 3500)),       # the top is never rounded above the stated figure
    (None, 4250, (500, 4200)),
])
def test_band_rule(budget, top, band):
    assert draft.price_band(budget, top) == band


def test_band_top_is_rounded_down_never_above_the_assessment():
    assert [draft.band_top(t) for t in (None, 2000, 3500, 3550, 4250, 8000)] == [3500, 3500, 3500, 3500, 4200, 8000]


def test_band_in_the_prompt_and_the_for_you_line():
    fake = FakeLLM(REPLY)
    out = draft.draft_reply(room(), QUESTION, TUESDAY, llm=fake)
    assert out["prompt"] == draft.FRAMEWORK_PROMPT
    user = fake.calls[0]["user"]
    assert "=== BEGIN PRICE_RANGE" in user and "$750 to $3,500" in user
    assert "=== BEGIN TIMELINE (computed) ===\nabout 2 weeks" in user
    assert "CALL_TIMES" not in user
    assert out["problems"] == [] and out["needs_you"] == [] and out["proposes_call"] is True
    assert ("Price range in this draft: $750 to $3,500 (low: posted budget $750; top: default top $3,500)"
            in out["for_you"])


def test_no_assessment_uses_the_default_range():
    facts = draft.framework_facts(room(notes="", budget=None))
    assert facts["band"] == (500, 3500) and facts["timeline"] is None
    assert draft.framework_for_you(facts) == [
        "Price range in this draft: $500 to $3,500 (low: no posted budget, default floor $500; top: default "
        "top $3,500)"]


@pytest.mark.parametrize("budget,shown", [(4000, "$4,000"), (3450, "$3,450")])
def test_a_budget_at_or_near_the_top_gives_no_range_and_needs_you(budget, shown):
    facts = draft.framework_facts(room(budget=budget))
    assert facts["band"] is None
    assert draft.framework_needs(room(budget=budget), facts)[0] == (
        "Price: their posted budget (%s) is at or near the top of the range ($3,500), so the draft gives no "
        "range. Set the price." % shown)


@pytest.mark.parametrize("text", [
    "We do $2M a year in revenue. How much would this cost?",
    "We spend $3,000 a month on ads, how long would the intake take?",
    "Would you be able to do $1,200 for the showroom intake?",
])
def test_client_figures_never_move_the_band(text):
    r = room(client_text=text, budget=None)
    facts = draft.framework_facts(r)
    assert facts["band"] == (500, 3500)
    assert any(n.startswith("Client mentioned $") and n.endswith("; check the range.")
               for n in draft.framework_needs(r, facts))


@pytest.mark.parametrize("text,figure", [
    ("Would 1,200 work for the showroom intake?", "1,200"),
    ("Our budget is 1500. How long would it take?", "1500"),
    ("Is EUR 1,000 ok for the showroom intake?", "EUR 1,000"),
])
def test_needs_you_names_every_client_price_as_written(text, figure):
    r = room(client_text=text, budget=None)
    assert draft.client_figures(r) == [figure]
    needs = draft.framework_needs(r, draft.framework_facts(r))
    assert "Client mentioned %s; check the range." % figure in needs
    assert not any("$1,000" in n for n in needs)


# ---------------------------------------------------------------- reading the assessment (real shapes)
@pytest.mark.parametrize("line,top", [
    ("- Defensible fixed range: **$4,200-$6,000**.", 6000),
    ("- $4,000 to $6,000 fixed for this scope built once and handed off.", 6000),
    ("- $4,000 to $6,000 fixed for this project.", 6000),
    ("- $4,000 to $6,000 fixed.", None),     # the plain form needs "for this scope / build / job / ..."
    ("- Most devs quote $4,000 to $6,000 fixed for this.", None),
    ("- Their previous developer charged $4,000 to $6,000 fixed for this scope.", None),
    ("- Other bidders: $4,000 to $6,000 fixed for this deliverable.", None),
    ("- Going rate: $4,000-$6,000 fixed for this job.", None),
    ("- Bigger shops quote $4,000 to $6,000 fixed for this build.", None),
    ("- Version 2: $4,000 to $6,000 fixed for this scope.", None),
    ("- Stage 2 (reporting): $4,000 to $6,000 fixed for this scope.", None),
    ("- Milestone 3: $4,000 to $6,000 fixed for this build.", None),
    ("- Expansion to all 12 locations: $4,000 to $6,000 fixed for this scope.", None),
    ("- With the SMS add-on: $4,000 to $6,000 fixed for this build.", None),
    ("- Worst case: $4,000 to $6,000 fixed for this job.", None),
    ("- Rush delivery: $4,000 to $6,000 fixed for this project.", None),
    ("- Upper end: $4,000 to $6,000 fixed for this project.", None),
    ("- $4,000 to $6,000 fixed for this scope (per location).", None),
    ("- Market for this scope: $50-$100/h x 16-20 h = $800-$2,000; agencies $4,500-$9,000 fixed.", None),
    ("- Their history: $4.8k over 391 hours, 58 contracts at $4,000 to $9,000 fixed.", None),
    ("- If it converts to build work: $5k to $10k fixed.", None),
    ("- Phase 2, the full platform: $18,000 to $40,000 fixed.", None),
    ("- A competent freelancer charges $1,500 to $4,000 fixed for a first integration.", None),
    ("- Building the integration afterwards: $3,000-6,000 fixed.", None),
    ("- Retainer: $1,500 to $4,000 a month.", None),
    ("- Option A $4,000 to $5,000 fixed.\n- Option B: $7,000 to $9,000 fixed.", None),
])
def test_assessed_fixed_top_reads_only_an_explicit_fixed_range_for_this_deliverable(line, top):
    assert draft.assessed_fixed_top("Standard pricing:\n" + line)[0] == top


@pytest.mark.parametrize("time_lines,phrase", [
    ("- The canvas build: 10 to 14 hours.\n- Their full list is an ongoing build: 4 to 8 weeks part-time.\n"
     "- Calendar for the first workflow: 1 to 1.5 weeks.", "about 2 weeks"),
    ("- Phase 1: 2 to 3 calendar weeks.\n- Phase 2 (automated follow-ups): 3 more weeks.", "about 3 weeks"),
    ("A single-channel sequence is 4 to 8 hours.", "within 2 days"),
    ("- Setup: 15-25 hours over about 2 weeks.\n- Ongoing: 5-10 hours a week.\n"
     "- First meetings realistically land 3-5 weeks after kickoff.", "about 2 weeks"),
    ("- Capture: 2 h\n- Matching: 1 h\n- CRM mapping: 3 h", None),
    ("- After that: about 10 to 20 hours a week running campaigns.", None),
    # the first deliverable wins whatever the line order; later phases are skipped
    ("- Stage 2 (reporting): 6 weeks.\n- Stage 1 (intake): 2 weeks.", "about 2 weeks"),
    ("- Rollout to the other 11 clinics: 8 weeks.\n- Pilot clinic: 2 weeks.", "about 2 weeks"),
    ("- Second workflow: 4 weeks.\n- This workflow: 5 days.", "within 5 days"),
    ("- First deliverable (the intake): 1 to 1.5 weeks.\n- Full build: 6 weeks.", "about 2 weeks"),
    ("- Version 2 with AI scoring: 6 weeks.\n- The intake: 1 week.", "about a week"),
    ("- Expansion to all locations: 10 weeks. Intake form: 3 days.", "within 3 days"),
    # two different answers are ambiguous: no timeline, it goes on NEEDS_YOU
    ("- Intake build: 2 weeks.\n- Reporting build: 4 weeks.", None),
])
def test_timeline_prefers_the_first_deliverable_and_skips_follow_on_work(time_lines, phrase):
    assert draft.timeline_phrase("Time:\n" + time_lines) == phrase


# ---------------------------------------------------------------- the gate: the band
@pytest.mark.parametrize("phrase", [
    "between $750 and $3,500", "$750 to $3,500", "$750-$3,500", "$750 to 3500",
    "between $750 and $3,500, and I aim to finish in about 2 weeks, faster if I clear my schedule for it",
])
def test_gate_accepts_exactly_the_band(phrase):
    body = "Thanks for getting back to me. For the showroom quote intake I'd put it %s." % phrase
    assert gate(body, room(client_text=NAMED)) == []


@pytest.mark.parametrize("body,code", [
    ("Thanks for getting back to me. For the showroom quote intake it would be $3,500.", "figure_not_in_offers"),
    ("Thanks for getting back to me. For the showroom intake I'd put it between $750 and $4,000.",
     "figure_not_in_offers"),
    ("Sure, $750 works for the showroom intake.", "agrees_to_client_price"),
    ("Sure, that works for the showroom intake. I'll confirm the exact price on the call.",
     "agrees_to_client_price"),
    ("For the showroom intake I'd put it at $750 to $3,500 a month.", "figure_not_in_offers"),
    ("For the showroom intake I'd put it at $750 to $3,500 an hour.", "figure_not_in_offers"),
    ("For the showroom intake I'd put it at $750 to $3,500 per workflow.", "figure_not_in_offers"),
    ("For the showroom intake I'd put it at $750 to $3,500/mo.", "figure_not_in_offers"),
    ("For the showroom intake I'd put it at $750 to $3,500 monthly.", "figure_not_in_offers"),
    ("For the showroom intake I'd put it at $750 to $3,500 for the build plus $750 to $3,500 for phase two.",
     "figure_not_in_offers"),
])
def test_gate_refuses_single_prices_off_band_figures_rates_and_their_number(body, code):
    assert code in gate(body, room(client_text=NAMED))


@pytest.mark.parametrize("tail", [
    "I'd put it at $750 to $3,500 for each workflow.",
    "I'd put it at $750 to $3,500 for every location.",
    "I'd put it at $750 to $3,500 (per workflow).",
    "I'd put it at $750 to $3,500 apiece.",
    "I'd put it at $750 to $3,500 a quarter.",
    "I'd put it at $750 to $3,500 quarterly.",
    "I'd put it at $750 to $3,500 on a monthly basis.",
    "I'd put it at $750 to $3,500, billed monthly.",
    "I'd put it at $750 to $3,500 USD a month.",
    "I'd put it at $750 to $3,500 in monthly fees.",
    "I'd put it at a monthly retainer of $750 to $3,500.",
    "per workflow it is $750 to $3,500.",
])
def test_a_rate_or_per_unit_cue_anywhere_in_the_sentence_unmasks_the_band(tail):
    body = "Thanks for getting back to me. For the showroom quote intake " + tail
    details = copy_gate.check_detailed(body, "reply", room(), draft.load_offers(), [NOTES], band=(750, 3500))
    assert [code for code, _ in details] == ["figure_not_in_offers"]
    assert "a rate or a per-unit price" in details[0][1]


@pytest.mark.parametrize("tail", [
    "$750 to $3,500, probably closer to 1,200.",
    "$750 to $3,500, likely around 2,000.",
    "$750 to $3,500, roughly 1500 for this one.",
    "$750 to $3,500, or a bit over two thousand.",
    "$750 to $3,500, around the midpoint.",
    "$750 to $3,500, most likely near the top end.",
])
def test_no_other_price_point_beside_the_range(tail):
    body = "Thanks for getting back to me. For the showroom quote intake I'd put it at " + tail
    assert "figure_not_in_offers" in gate(body)


def test_without_a_band_the_gate_still_refuses_the_range():
    body = "Thanks for getting back to me. For the showroom quote intake I'd put it between $750 and $3,500."
    assert "figure_not_in_offers" in copy_gate.check(body, "reply", room(), draft.load_offers(), [NOTES])


# ---------------------------------------------------------------- the gate: never agree to their figure
@pytest.mark.parametrize("body", [
    "Sure, that works. The range is $750 to $3,500.",
    "Yes, I can do that. I'd put it between $750 and $3,500.",
    "Happy to work within your budget. I'd put it between $750 and $3,500.",
    "Thanks for getting back to me. Sure, that works for the showroom intake. I'll confirm the exact price on a "
    "brief Upwork call.",
    "Thanks for getting back to me. Deal, the showroom intake it is.",
    "Thanks for getting back to me. I can work with your budget on the showroom intake. I'd put it between $750 "
    "and $3,500.",
    "Thanks for getting back to me. I'd put it between $750 and $3,500. Sure, that works, does Thursday at 1pm ET "
    "suit you?",
])
def test_a_framework_reply_never_agrees_to_their_figure(body):
    r = room(client_text=NAMED)
    assert "agrees_to_client_price" in gate(body, r)
    assert "agrees_to_client_price" in gate(body, r, band=None, framework=True)


REPRO = ("Thanks for getting back to me. That works for the showroom intake. I aim to finish in about 2 weeks, "
         "faster if I clear my schedule for it. I'll confirm the exact price on a brief Upwork call, where you'd "
         "leave with the scope and a walk through the HubSpot setup. I'm free now, in the next couple of hours, "
         "or tomorrow at 1pm ET (noon CT).")


def test_a_deferral_never_cancels_the_agreement_check_without_a_range():
    r = room(client_text="Would $4,000 work for the showroom intake? How long would it take?", budget=4000)
    assert draft.framework_facts(r)["band"] is None      # no range: the framework flag turns the check on
    assert gate(REPRO, r, band=None, framework=True) == ["agrees_to_client_price"]
    output = REPRO + "\nNEEDS_YOU:\n- none\nPROPOSES_CALL: yes"
    out = draft.draft_reply(r, QUESTION, TUESDAY, llm=FakeLLM(output, output))
    assert out["prompt"] == draft.FRAMEWORK_PROMPT and out["attempts"] == 2
    assert out["problems"] == ["agrees_to_client_price"]
    assert out["needs_you"][0].startswith("Price: their posted budget ($4,000)")


@pytest.mark.parametrize("body", [
    REPLY.split("\nNEEDS_YOU:", 1)[0],
    "Thanks for getting back to me. It's doable in about 2 weeks for the showroom intake. I'd put it at $750 to "
    "$3,500.",
    "Thanks for getting back to me. I can do that in HubSpot, and the showroom intake form feeds it directly. The "
    "range is $750 to $3,500.",
    "Thanks for getting back to me. That's great to hear about the showroom intake. I'd put it between $750 and "
    "$3,500.",
    "Thanks for getting back to me. This works by tagging each showroom intake request by tile line in HubSpot. "
    "I'd put it between $750 and $3,500.",
    "Thanks for getting back to me. Everything is built in your own HubSpot account, so you own the account and "
    "the IP for the showroom intake, and I join as a team member. I'd put it between $750 and $3,500.",
])
def test_framework_replies_that_do_not_agree_pass(body):
    assert gate(body, room(client_text=NAMED)) == []


# ---------------------------------------------------------------- routing: the classifier's label
@pytest.mark.parametrize("label,framework", [
    ("question", True), ("positive", False), ("neutral", False), ("not_now", False), ("machine", False)])
def test_the_classifier_label_alone_picks_the_framework(label, framework):
    r = room(client_text="How much would the showroom intake cost? How long would it take?")
    assert draft.is_framework_reply(r, labelled(("m2", label))) is framework


@pytest.mark.parametrize("text", [
    "Thanks for the video. We need an estimate follow-up that texts the homeowner.",
    "Great. We have a budget approved for this.",
    "Thanks, this shows how much time our office wastes on callbacks.",
    "What's needed is the intake by Friday.",
    "How about we start Monday.",
])
def test_statements_never_route_to_the_framework(text):
    # prompts/classify.md labels these positive or neutral; no regex reads the text for routing.
    r = room(client_text=text)
    assert draft.is_framework_reply(r) is False
    for label in ("positive", "neutral"):
        assert draft.is_framework_reply(r, labelled(("m2", label))) is False


@pytest.mark.parametrize("text", ["Send me a quote", "How long would it take", "Can you do it by Friday"])
def test_direct_asks_route_when_the_classifier_says_question(text):
    r = room(client_text=text)
    assert draft.is_framework_reply(r) is False         # no label recorded: the plain reply
    assert draft.is_framework_reply(r, labelled(("m2", "question"))) is True


def test_only_labels_of_unanswered_client_messages_count():
    r = room(client_text="Thanks, I'll watch the video tonight.")
    r["messages"].insert(0, {"id": "m0", "side": "client", "at": "2026-10-04T15:00:00Z", "text": "How much?"})
    # m0 was answered by Lorenzo's m1, so its question label is stale
    assert draft.is_framework_reply(r, labelled(("m0", "question"), ("m2", "positive"))) is False
    assert draft.is_framework_reply(r, labelled(("m0", "question"))) is False
    assert draft.is_framework_reply(r, labelled(("m2", None))) is False
    # every unanswered message counts, whichever burst labelled it
    r["messages"].append({"id": "m3", "side": "client", "at": "2026-10-06T14:10:00Z", "text": "Thanks again."})
    assert draft.unanswered_labels(r, labelled(("m2", "question"), ("m3", "positive"))) == ["positive", "question"]
    assert draft.is_framework_reply(r, labelled(("m2", "question"), ("m3", "positive"))) is True
    # recorded while Lorenzo had stopped the thread
    assert draft.is_framework_reply(r, labelled(("m3", "question", "client_message_while_stopped"))) is True
    # any other history event is not a classifier label
    assert draft.is_framework_reply(r, labelled(("m3", "question", "reply_sent"))) is False


@pytest.mark.parametrize("label,framework", [("question", True), ("positive", False)])
def test_the_label_sequence_records_drives_the_route(label, framework):
    r = room(client_text="Looks great, can you do it by Friday")
    seen = []

    def classify(text, _room):
        seen.append(text)
        return {"label": label, "confidence": 0.95}

    thread, _acts = sequence.advance(sequence.new_thread(r, TUESDAY), r, TUESDAY, classify)
    assert seen == ["Looks great, can you do it by Friday"]
    assert draft.unanswered_labels(r, thread) == [label]
    assert draft.is_framework_reply(r, thread) is framework


def test_classify_prompt_returns_question_for_direct_asks_and_never_for_statements():
    text = (draft.PROMPTS_DIR / "classify.md").read_text(encoding="utf-8")
    question = next(ln for ln in text.splitlines() if ln.startswith("- question:"))
    assert "without a question mark" in question
    for ask in ("send me a quote", "how long would it take", "can you do it by Friday"):
        assert ask in question
    statements = text.split("## Questions and statements", 1)[1].split("\n## ", 1)[0]
    for statement in ("We need an estimate follow-up that texts the homeowner", "We have a budget approved",
                      "This shows how much time our office wastes", "What's needed is the intake by Friday",
                      "How about we start Monday"):
        assert statement in statements
    assert "positive or neutral, never question" in statements


@pytest.mark.parametrize("thread", [None, labelled(("m2", "positive"))])
def test_a_reply_without_the_question_label_keeps_the_three_times(thread):
    fake = FakeLLM("Sounds good, the showroom intake part is the first two minutes.\nNEEDS_YOU:\n- none\n"
                   "PROPOSES_CALL: no")
    out = draft.draft_reply(room(), thread, TUESDAY, llm=fake)
    assert out["prompt"] == "reply.md"
    assert "=== BEGIN CALL_TIMES" in fake.calls[0]["user"] and "PRICE_RANGE" not in fake.calls[0]["user"]


# ---------------------------------------------------------------- the call offer
def test_framework_call_offer_wording():
    assert draft.framework_call_offer(TUESDAY, room()) == (
        "now, in the next couple of hours, or tomorrow at 1pm ET (noon CT)")
    assert draft.framework_call_offer(FRIDAY, room()) == (
        "now, in the next couple of hours, or Monday at 1pm ET (noon CT)")
    assert draft.framework_call_offer(TUESDAY, room(location=None)) == (
        "now, in the next couple of hours, or tomorrow at noon CT")


def test_posted_budget_is_read_from_the_jd_summary():
    jd = "url: https://www.upwork.com/jobs/~02x\nIntake\nFixed price $750, entry level.\n\nThe post.\n"
    assert collect.parse_jd(jd)["budget"] == 750
    assert collect.parse_jd(jd.replace("Fixed price $750", "Hourly $20-$35"))["budget"] is None


def test_framework_prompt_is_ascii_and_states_the_framework():
    text = (draft.PROMPTS_DIR / draft.FRAMEWORK_PROMPT).read_text(encoding="utf-8")
    assert all(ord(c) < 128 for c in text)
    for needle in ("Thank them", "PRICE_RANGE", "I aim to finish", "they own the accounts and the IP",
                   "CALL_OFFER", "Never agree to or accept a price", "On-platform rule", "How Lorenzo writes",
                   "Say the thing and stop", "never more than 1,500"):
        assert needle in text
    section = text.split("## How Lorenzo writes", 1)[1].split("\n## ", 1)[0]
    examples = [ln for ln in section.splitlines() if ln.startswith('- "')]
    assert len(examples) == 5
    for ex in examples:
        assert not any(ch.isdigit() for ch in ex)
        assert "!" not in ex
        assert " we " not in ex.lower() and "so you only pay" not in ex
    assert "What is going to be your sending volume?" in section
    assert "As for connecting the two accounts" not in section


# ---------------------------------------------------------------- the weekend watch
def test_weekend_watch_plan(store, monkeypatch):
    assert watch.WATCH_DAYS == (0, 1, 2, 3, 4, 5, 6)
    assert watch.watch_cron() == ["*/30 8-18 * * *", "0 19 * * *"]
    prompt = tw.PROMPT.read_text(encoding="utf-8")
    assert all(line in prompt for line in watch.watch_cron())
    # Saturday with an older snapshot: the day's first run is a full collect, not skipped.
    assert tw.plan(tw.quiet_cards(), store=store, now=SATURDAY)["mode"] == "full"
    monkeypatch.setattr(watch, "WATCH_DAYS", (0, 1, 2, 3, 4))
    assert tw.plan(tw.quiet_cards(), store=store, now=SATURDAY)["mode"] == "none"


@pytest.fixture
def store(tmp_path):
    from shared.store import get_store
    s = get_store(force_new=True)
    tw.mark_processed(s, tw.snapshot())     # the snapshot is Tuesday 2026-09-22's full collect
    return s
