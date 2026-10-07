"""The setter-framework reply (Lorenzo, 2026-10-05), its price band (Lorenzo,
2026-10-06: $500 to $3,500 by default, never below $500), routing, and the
weekend watch. Every model call is an injected fake; nothing here spends a
token. Invented clients and invented assessment lines only (shapes taken from
real assessments)."""
from datetime import datetime, timezone

import pytest

from services.upwork_followup import collect, copy_gate, draft, watch
from services.upwork_followup.tests import test_watch as tw

TUESDAY = datetime(2026, 10, 6, 15, 0, tzinfo=timezone.utc)     # Tuesday 10:00 CT
FRIDAY = datetime(2026, 10, 9, 20, 0, tzinfo=timezone.utc)      # Friday 15:00 CT
SATURDAY = datetime(2026, 10, 10, 17, 0, tzinfo=timezone.utc)   # Saturday 12:00 CT

NOTES = ("Time:\n- 4 to 8 hours, 1 to 2 calendar weeks.\n\n"
         "Standard pricing:\n- Market for this intake: $1,000 to $2,500 fixed.\n"
         "- Recurring software: HubSpot Starter about $20 a month.")


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


REPLY = ("Thanks for getting back to me. For the showroom quote intake I'd put it between $750 and $3,500, and "
         "I aim to finish in about 2 weeks, faster if I clear my schedule for it. The range isn't complete yet: "
         "I need your HubSpot tier and how many website forms feed it. On a brief Upwork call you'd leave with "
         "the scope, I'd walk you through how the setup works, and it's a free consult on anything related. I'm "
         "free now, in the next couple of hours, or tomorrow at 1pm ET (noon CT).\n"
         "NEEDS_YOU:\n- none\nPROPOSES_CALL: yes")


# ---------------------------------------------------------------- the band
@pytest.mark.parametrize("budget,top,band", [
    (None, None, (500, 3500)),       # no budget, no assessment: the default
    (750, None, (750, 3500)),        # $750 budget, no assessment
    (300, None, (500, 3500)),        # never below $500
    (1977, None, (1900, 3500)),      # rounded down to a clean number
    (5000, 6000, (5000, 6000)),      # the assessment raised the top
    (3500, None, None),              # the budget reaches the top: no range
])
def test_band_rule(budget, top, band):
    assert draft.price_band(budget, top) == band


def test_band_in_the_prompt_and_the_for_you_line():
    fake = FakeLLM(REPLY)
    out = draft.draft_reply(room(), None, TUESDAY, llm=fake)
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


def test_a_budget_at_the_top_gives_no_range_and_needs_you():
    facts = draft.framework_facts(room(budget=4000))
    assert facts["band"] is None
    assert draft.framework_needs(room(budget=4000), facts)[0].startswith("Price: their posted budget ($4,000)")


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


# ---------------------------------------------------------------- reading the assessment (real shapes)
@pytest.mark.parametrize("line,top", [
    ("- Defensible fixed range: **$4,200-$6,000**.", 6000),
    ("- $4,000 to $6,000 fixed for this scope built once and handed off.", 6000),
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
])
def test_timeline_prefers_the_first_deliverable_and_skips_follow_on_work(time_lines, phrase):
    assert draft.timeline_phrase("Time:\n" + time_lines) == phrase


# ---------------------------------------------------------------- the gate
@pytest.mark.parametrize("phrase", ["between $750 and $3,500", "$750 to $3,500", "$750-$3,500", "$750 to 3500"])
def test_gate_accepts_exactly_the_band(phrase):
    r = room(client_text="Would $750 work for the showroom intake? How long would it take?")
    body = "Thanks for getting back to me. For the showroom quote intake I'd put it %s." % phrase
    assert copy_gate.check(body, "reply", r, draft.load_offers(), [NOTES], band=(750, 3500)) == []


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
])
def test_gate_refuses_single_prices_off_band_figures_rates_and_their_number(body, code):
    r = room(client_text="Would $750 work for the showroom intake? How long would it take?")
    assert code in copy_gate.check(body, "reply", r, draft.load_offers(), [NOTES], band=(750, 3500))


def test_without_a_band_the_gate_still_refuses_the_range():
    body = "Thanks for getting back to me. For the showroom quote intake I'd put it between $750 and $3,500."
    assert "figure_not_in_offers" in copy_gate.check(body, "reply", room(), draft.load_offers(), [NOTES])


# ---------------------------------------------------------------- routing
@pytest.mark.parametrize("text,asks", [
    ("Here's our form: https://example.com/form?id=3 for reference.", False),
    ("What I need is the intake done by Friday.", False),
    ("When I watched the video I liked it.", False),
    ("How exciting. I'll review with my partner.", False),
    ("So what we want is the quotes in HubSpot.", False),
    ("Have the build ready when you can.", False),
    ("Thanks, I'll watch the video tonight.", False),
    ("Hi, how much would you charge for this", True),
    ("Hey Lorenzo, what's your timeline", True),
    ("Thanks for the video, how long would it take", True),
    ("Looks great, can you do it by Friday", True),
    ("Send me a quote", True),
    ("Let me know your price and timeline", True),
    ("Does it work with HubSpot Starter?", True),
])
def test_routing_to_the_framework(text, asks):
    assert draft.is_framework_reply(room(client_text=text)) is asks


def test_the_classifier_question_label_routes_to_the_framework():
    thread = {"history": [{"at": "2026-10-06T14:05:00Z", "event": "client_reply", "message_id": "m2",
                           "label": "question"}]}
    assert draft.is_framework_reply(room(client_text="Thanks, I'll watch the video tonight."), thread) is True


def test_a_reply_with_no_question_keeps_the_three_times():
    r = room(client_text="Thanks, I'll watch the video tonight.")
    fake = FakeLLM("Sounds good, the showroom intake part is the first two minutes.\nNEEDS_YOU:\n- none\n"
                   "PROPOSES_CALL: no")
    out = draft.draft_reply(r, None, TUESDAY, llm=fake)
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
        assert " we " not in ex.lower() and "so you only pay" not in ex


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
