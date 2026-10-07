"""The setter-framework reply (Lorenzo, 2026-10-05) and its computed price band
(2026-10-06), plus the weekend watch. Every model call is an injected fake;
nothing here spends a token. Invented clients only."""
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


REPLY = ("Thanks for getting back to me. For the showroom quote intake I'd put it between $750 and $1,000, and "
         "I aim to finish in about 2 weeks, faster if I clear my schedule for it. The range isn't complete yet: "
         "I need your HubSpot tier and how many website forms feed it. On a brief Upwork call you'd leave with "
         "the scope, I'd walk you through how the setup works, and it's a free consult on anything related. I'm "
         "free now, in the next couple of hours, or tomorrow at 1pm ET (noon CT).\n"
         "NEEDS_YOU:\n- none\nPROPOSES_CALL: yes")


# ---------------------------------------------------------------- the band
def test_band_from_the_assessment_with_a_budget_under_the_standard_price():
    assert draft.standard_price(NOTES) == 1000          # the low end of the market range; software skipped
    assert draft.price_band(1000, 750) == (750, 1000)
    assert draft.price_band(1250, 1977) == (1000, 2000)  # budget above standard: 80% low, budget high
    assert draft.price_band(3500, None) == (2800, 3500)  # no budget: about 80% of standard
    assert draft.price_band(1500, 1140) == (1100, 1500)  # budget rounded down to a clean number
    fake = FakeLLM(REPLY)
    out = draft.draft_reply(room(), None, TUESDAY, llm=fake)
    assert out["prompt"] == draft.FRAMEWORK_PROMPT
    user = fake.calls[0]["user"]
    assert "=== BEGIN PRICE_RANGE" in user and "$750 to $1,000" in user
    assert "=== BEGIN TIMELINE (computed) ===\nabout 2 weeks" in user
    assert "CALL_TIMES" not in user
    assert out["problems"] == [] and out["needs_you"] == [] and out["proposes_call"] is True
    assert "Price range in this draft: $750 to $1,000 (standard $1,000, budget $750)" in out["for_you"]


def test_no_assessment_means_no_dollars_and_the_price_goes_on_needs_you():
    r = room(notes="", budget=None)
    assert draft.framework_facts(r)["band"] is None
    leaky = REPLY.replace("between $750 and $1,000", "at $900")
    fake = FakeLLM(leaky, leaky)
    out = draft.draft_reply(r, None, TUESDAY, llm=fake)
    assert "none: write no dollar figure and put the price on NEEDS_YOU" in fake.calls[0]["user"]
    assert "figure_not_in_offers" in out["problems"]
    assert out["needs_you"][0].startswith("Price: they asked")
    assert out["needs_you"][1].startswith("Timeline: they asked")


# ---------------------------------------------------------------- the gate
@pytest.mark.parametrize("phrase", ["between $750 and $1,000", "$750 to $1,000", "$750-$1,000", "$750 to 1000"])
def test_gate_accepts_exactly_the_band(phrase):
    r = room(client_text="Would $750 work for the showroom intake? How long would it take?")
    body = "Thanks for getting back to me. For the showroom quote intake I'd put it %s." % phrase
    assert copy_gate.check(body, "reply", r, draft.load_offers(), [NOTES], band=(750, 1000)) == []


@pytest.mark.parametrize("body,code", [
    ("Thanks for getting back to me. For the showroom quote intake it would be $1,000.", "figure_not_in_offers"),
    ("Thanks for getting back to me. For the showroom intake I'd put it between $750 and $1,200.",
     "figure_not_in_offers"),
    ("Sure, $750 works for the showroom intake.", "agrees_to_client_price"),
    ("Sure, that works for the showroom intake. I'll confirm the exact price on the call.",
     "agrees_to_client_price"),
])
def test_gate_refuses_a_single_price_an_off_band_figure_and_their_number(body, code):
    r = room(client_text="Would $750 work for the showroom intake? How long would it take?")
    assert code in copy_gate.check(body, "reply", r, draft.load_offers(), [NOTES], band=(750, 1000))


def test_without_a_band_the_gate_still_refuses_the_range():
    body = "Thanks for getting back to me. For the showroom quote intake I'd put it between $750 and $1,000."
    assert "figure_not_in_offers" in copy_gate.check(body, "reply", room(), draft.load_offers(), [NOTES])


# ---------------------------------------------------------------- the call offer
def test_framework_call_offer_wording():
    assert draft.framework_call_offer(TUESDAY, room()) == (
        "now, in the next couple of hours, or tomorrow at 1pm ET (noon CT)")
    assert draft.framework_call_offer(FRIDAY, room()) == (
        "now, in the next couple of hours, or Monday at 1pm ET (noon CT)")
    assert draft.framework_call_offer(TUESDAY, room(location=None)) == (
        "now, in the next couple of hours, or tomorrow at noon CT")


def test_a_reply_with_no_question_keeps_the_three_times():
    r = room(client_text="Thanks, I'll watch the video tonight.")
    fake = FakeLLM("Sounds good, the showroom intake part is the first two minutes.\nNEEDS_YOU:\n- none\n"
                   "PROPOSES_CALL: no")
    out = draft.draft_reply(r, None, TUESDAY, llm=fake)
    assert out["prompt"] == "reply.md"
    assert "=== BEGIN CALL_TIMES" in fake.calls[0]["user"] and "PRICE_RANGE" not in fake.calls[0]["user"]


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
