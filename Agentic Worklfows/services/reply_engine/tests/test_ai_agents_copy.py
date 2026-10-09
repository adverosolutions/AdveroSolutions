"""The AI agents reply copy Lorenzo approved on 2026-10-06 (offer key ai_agents).

One test per path: each approved first reply renders his text exactly, the
price band is allowed only in the pricing reply, the booking URL only in the
booking_link reply, "AI agents" passes the copy gate, the older offers' first
replies stay held, the follow-up lines render, and E1 goes out with no Veto
window.
"""
import json
import os
import sys
from datetime import datetime

import httpx
import pytest

from shared import settings
from shared.instantly import Instantly
from shared.settings import TZ

from services.reply_engine import cadence, draft
from services.reply_engine import template_approvals as ta
from services.reply_engine.cadence import LeadState
from services.reply_engine.models import Classification, Extracted, ReplyEvent

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "tools", "template_doc"))
import doc_rules  # noqa: E402

PEST_CONTROL_AI = "21f5568a-d82e-4280-8437-04b0f8d6df37"
AI_CAMPAIGNS = (
    "e8867dbb-4f94-40ee-81c0-c11d7a256e2d", "d81f1d53-23d6-48a6-aea3-80c21192e17e",
    "9b82c9ce-b772-440a-b4a0-b984fe6a7a3f", "8a50b4e8-48e7-4db2-aa8f-b2e75187a8be",
    "891bf2b5-9351-4cde-a5c4-13dd1d8ffce8", "59b20790-12bb-446d-bcd6-e3b6f9a61953",
    "4eedb228-53c7-42ff-baf5-5b40c8646bd8", PEST_CONTROL_AI,
)
URL = "https://api.leadconnectorhq.com/widget/booking/GDugwLmZNdsD13RBDnRu"
SAMPLE = {"first_name": "Dana", "company": "Greenway Pest Control",
          "slots": "Thu 2:00pm CT (3:00pm ET your time) or Fri 3:00pm CT (4:00pm ET your time)"}

# Verbatim from the approved copy file (approved_copy_ai_agents_2026-10-06.md),
# with the sample values in place.
APPROVED = {
    "first_reply.ai_agents.default.full": (
        "Hey Dana,\n\n"
        "Glad to hear it. Would Thu 2:00pm CT (3:00pm ET your time) or Fri 3:00pm CT (4:00pm ET your time) work "
        "for a 15 minute call?\n\n"
        "Lorenzo"),
    "first_reply.ai_agents.mechanism.full": (
        "Hey Dana,\n\n"
        "Glad you asked. Quick overview: I look at how Greenway Pest Control runs day to day, find the tasks AI "
        "agents can take over, and put that in a plan with what each one is worth in time and money. If you like "
        "it, I build them. If not, the plan is yours to keep.\n\n"
        "Would Thu 2:00pm CT (3:00pm ET your time) or Fri 3:00pm CT (4:00pm ET your time) work for a 15 minute "
        "call?\n\n"
        "Lorenzo"),
    "first_reply.ai_agents.send_info.full": (
        "Hey Dana,\n\n"
        "Most of what I'd send depends on how Greenway Pest Control runs, so it's quicker to cover on a call. Short "
        "version: I find the tasks AI agents can take over and show you what each one is worth in time and money. "
        "The plan is free and yours to keep.\n\n"
        "Would Thu 2:00pm CT (3:00pm ET your time) or Fri 3:00pm CT (4:00pm ET your time) work for a 15 minute "
        "call?\n\n"
        "Lorenzo"),
    "first_reply.ai_agents.pricing.full": (
        "Hey Dana,\n\n"
        "The plan itself is free and yours to keep. Builds after that usually land between $400 and $5,300, "
        "depending on how many agents make sense for Greenway Pest Control.\n\n"
        "Would Thu 2:00pm CT (3:00pm ET your time) or Fri 3:00pm CT (4:00pm ET your time) work for a 15 minute "
        "call? I'll have the exact number for you by the end of it.\n\n"
        "Lorenzo"),
    "first_reply.ai_agents.booking_link.full": (
        "Hey Dana,\n\n"
        "Would Thu 2:00pm CT (3:00pm ET your time) or Fri 3:00pm CT (4:00pm ET your time) work for a 15 minute "
        "call? If neither fits, here's my calendar: " + URL + "\n\n"
        "Lorenzo"),
}
LINES = {
    "cadence.e2.research_fallback.ai_agents":
        "The quickest place to start is usually wherever the most money is slipping through right now.",
    "cadence.e4.offer_proof.ai_agents":
        "a team of AI agents for a $150M/year commercial roofer that won back about $6M in 6 months",
    "cadence.e5.offer_line.ai_agents":
        "use AI agents to bring in more revenue and give your team hours back each week",
    "cadence.e6.preview.ai_agents":
        "The tasks your team does every week that an agent could take over, what each one is worth in hours and "
        "dollars, and the order I'd build them in.",
    "cadence.e9.observation.ai_agents":
        "Quotes and proposals that went out and never got an answer are usually the first thing I'd hand to an "
        "agent.",
}
QT = {"default": None, "mechanism": "mechanism", "send_info": "send_info", "pricing": "pricing",
      "booking_link": "booking_link"}


def ct(*args):
    return TZ.localize(datetime(*args))


@pytest.fixture(scope="module")
def index():
    return ta.catalogue_index()


def _event(campaign_id=PEST_CONTROL_AI):
    meta = settings.CAMPAIGN_BY_ID[campaign_id]
    return ReplyEvent(email_id="e-1", lead_email="dana@greenway.example", campaign_id=campaign_id,
                      campaign_key=meta["key"], niche=meta.get("niche"), offer=meta.get("offer"),
                      first_name="Dana", company="Greenway Pest Control", subject="Dana, question", text="",
                      received_at=ct(2030, 1, 7, 9, 0))


def _cls(branch):
    if branch == "default":
        return Classification(label="positive_interested", confidence=0.95, extracted=Extracted())
    return Classification(label="positive_question", confidence=0.95, extracted=Extracted(question_type=QT[branch]))


def test_every_ai_agents_campaign_maps_to_the_offer_and_none_is_in_campaigns():
    for cid in AI_CAMPAIGNS:
        assert settings.CAMPAIGN_BY_ID[cid]["key"] == "ai_agents"
    # never where the poller filter and the change-sets read campaign ids
    listed = set(v.get("id") for v in settings.CAMPAIGNS.values())
    assert not listed & set(AI_CAMPAIGNS) and len(settings.CAMPAIGNS) == 6


@pytest.mark.parametrize("tid", sorted(APPROVED))
def test_each_approved_first_reply_renders_lorenzos_text_exactly(index, tid):
    entry = index[tid]
    assert entry["approvable"] and not doc_rules.is_held(tid)
    assert ta.fill(entry["text"], **SAMPLE).rstrip("\n") == APPROVED[tid]
    # and the engine's own render of it is that template, clean
    branch = tid.split(".")[2]
    d = draft.build_draft(_event(), _cls(branch), now=ct(2030, 1, 7, 9, 0), use_llm=False, busy_blocks=[])
    assert d.template_id == tid and d.problems == []


def test_the_price_band_passes_only_in_the_pricing_reply(index):
    body = ta.fill(index["first_reply.ai_agents.pricing.full"]["text"], **SAMPLE)
    assert draft.validate_draft(body, campaign_key="ai_agents", first_reply=True, pricing_reply=True) == []
    refused = draft.validate_draft(body, campaign_key="ai_agents", first_reply=True)
    assert draft.PRICING_REPLY_ONLY_PROBLEM % "400" in refused and draft.PRICING_REPLY_ONLY_PROBLEM % "5300" in refused
    assert draft.template_gate_flags("first_reply.ai_agents.pricing.full") == {"pricing_reply": True}
    assert draft.template_gate_flags("first_reply.ai_agents.default.full") == {}
    touch = "Hey Dana,\n\nBuilds usually land between $400 and $5,300.\n\nLorenzo"
    assert "money_pricing_reply_only" in cadence.copy_problems(touch, campaign_key="ai_agents")
    # another offer's thread: it is the ai_agents band, not theirs
    assert any("ai_agents" in p for p in draft.validate_draft(touch, campaign_key="cleaning_reactivation"))


def test_the_booking_url_passes_only_in_the_booking_link_reply(index):
    body = ta.fill(index["first_reply.ai_agents.booking_link.full"]["text"], **SAMPLE)
    assert draft.validate_draft(body, campaign_key="ai_agents", first_reply=True, allowed_url=URL) == []
    assert "contains a booking link" in draft.validate_draft(body, campaign_key="ai_agents", first_reply=True)
    assert draft.template_gate_flags("first_reply.ai_agents.booking_link.full") == {"allowed_url": URL}
    other = ta.fill(index["first_reply.ai_agents.mechanism.full"]["text"], **SAMPLE).replace(
        "\n\nLorenzo", " " + URL + "\n\nLorenzo")
    assert "contains a booking link" in draft.validate_draft(
        other, campaign_key="ai_agents", first_reply=True, **draft.template_gate_flags(
            "first_reply.ai_agents.mechanism.full"))
    # the allowance is that URL only
    assert "contains a booking link" in draft.validate_draft(
        body.replace(URL, "https://calendly.com/someone"), campaign_key="ai_agents", first_reply=True, allowed_url=URL)


def test_ai_agents_passes_the_copy_gate_and_a_bot_still_does_not():
    body = "Hey Dana,\n\nI build AI agents and automation for service businesses.\n\nLorenzo"
    assert draft.validate_draft(body, campaign_key="ai_agents") == []
    assert cadence.copy_problems(body, campaign_key="ai_agents") == []
    for bad in ("a bot wrote this", "GPT drafted it", "an LLM", "a chatbot", "machine learning", "an algorithm"):
        text = "Hey Dana,\n\nThis is %s.\n\nLorenzo" % bad
        assert draft.validate_draft(text), bad
        assert "mentions_ai_or_automation" in cadence.copy_problems(text), bad


def test_older_offers_first_replies_stay_held_and_ai_referral_and_other_are_not_approvable(index):
    old = [t for t in index if t.startswith("first_reply.") and t.endswith(".full") and ".ai_agents." not in t]
    assert len(old) == 36
    assert all(doc_rules.is_held(t) for t in old)
    for branch in ("referral", "other"):
        tid = "first_reply.ai_agents.%s.full" % branch
        assert not index[tid]["approvable"] and doc_rules.is_held(tid)
    assert sorted(doc_rules.APPROVED_FIRST_REPLIES) == sorted(APPROVED)


def test_ai_agents_follow_up_lines_render(index):
    for tid, line in LINES.items():
        assert index[tid]["approvable"] and index[tid]["text"] == line
    state = LeadState(lead_email="dana@greenway.example", campaign_id=PEST_CONTROL_AI, first_name="Dana",
                      company="Greenway Pest Control LLC", last_subject="Re: Dana, question")
    two = ["2030-01-08T14:00:00-06:00", "2030-01-10T15:00:00-06:00"]
    for day, tid in ((2, "cadence.e2.research_fallback.ai_agents"), (4, "cadence.e4.offer_proof.ai_agents"),
                     (5, "cadence.e5.offer_line.ai_agents"), (6, "cadence.e6.preview.ai_agents"),
                     (9, "cadence.e9.observation.ai_agents")):
        touch = cadence.build_touch(state, day, two)
        assert list(touch.template_parts) == [tid] and LINES[tid] in touch.body_text
        assert touch.problems == [] and cadence.missing_lead_data(state, day) == []


def test_e1_goes_out_at_ten_with_no_veto_window(tmp_path, live_mode, tmp_env, monkeypatch):
    from shared.store import JsonFileStore

    monkeypatch.delenv("BASE_URL", raising=False)
    monkeypatch.delenv("REPLY_ENGINE_BASE_URL", raising=False)
    store = JsonFileStore(tmp_path / "store.json")
    posts = []

    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, json={"id": "e-1", "from_address_email": "tiffany@flowerhillfs.com"})
        posts.append(json.loads(request.content or b"{}"))
        return httpx.Response(200, json={"id": "sent-1"})

    inst = Instantly(api_key="x", transport=httpx.MockTransport(handler))
    state = cadence.arm(LeadState(lead_email="tiffany@flowerhillfs.com", campaign_id="8086b41e-b546-4b36-9fa0-2d01f5cc119a",
                                  status="positive_interested", first_name="Tiffany",
                                  company="Flowerhill Facility Services", eaccount="lorenzo@adveromedia.com",
                                  thread_id="thr-1", last_email_id="01a0c5aa-0000-7000-8000-000000000001",
                                  last_subject="Re: Tiffany, question"), ct(2026, 9, 21, 16, 0))
    free = ["2026-09-23T13:00:00-05:00", "2026-09-24T14:00:00-05:00"]
    pings = []
    res = cadence.tick_lead(state, ct(2026, 9, 22, 9, 30), store=store, instantly=inst, free_slots=free,
                            notify_fn=lambda *a, **k: pings.append((a, k)))
    assert res["action"] == "not_due" and not pings and not posts
    res = cadence.tick_lead(state, ct(2026, 9, 22, 10, 0), store=store, instantly=inst, free_slots=free,
                            notify_fn=lambda *a, **k: pings.append((a, k)))
    assert res["action"] == "sent" and len(posts) == 1
    assert not any("Veto" in str(p) for p in pings)
    assert not (state.cadence or {}).get("veto_notified_at")


def test_an_ai_agents_call_never_gets_a_clean_brief_or_proposal_for_another_offer():
    from services.reply_engine import precall, proposal, show_rate

    appt = {"id": "appt-ai", "contact_id": "c-1", "start_iso": "2026-09-23T11:30:00-05:00",
            "email": "dana@greenway.example", "first_name": "Dana", "company": "Greenway Pest Control",
            "campaign_id": PEST_CONTROL_AI}
    resolved = precall.resolve_offer(appt)
    assert resolved["campaign_matched"] and resolved["offer"] == "ai_agents" and resolved["offer_block_missing"]
    brief = precall.build_brief(appt, ct(2026, 9, 23, 10, 30), instantly=None, read_thread=False)
    assert resolved["offer_block_missing"] in brief.problems
    built = proposal.build_proposal(appt, ct(2026, 9, 23, 12, 0), inputs=proposal.CallInputs(), use_llm=False)
    assert resolved["offer_block_missing"] in built.problems
    # even when the brief's key is handed over
    built = proposal.build_proposal(dict(appt, campaign_id=None), ct(2026, 9, 23, 12, 0),
                                    inputs=proposal.CallInputs(), use_llm=False, campaign_key="ai_agents")
    assert any("has no pricing or proposal block" in p for p in built.problems)
    assert show_rate.offer_of(appt) == "ai_agents"


def test_show_rate_and_no_show_emails_for_an_ai_agents_lead_hold():
    from services.reply_engine import show_rate

    appt = {"id": "appt-ai", "start_iso": "2030-01-08T13:47:00-06:00", "first_name": "Dana",
            "company": "Greenway Pest Control", "campaign_id": PEST_CONTROL_AI}
    for key in ta.SHOW_RATE_LEAD_FACING:
        assert show_rate.resolve_template_id(key, appt) is None, key
    for key in ta.NO_SHOW_LEAD_FACING:
        assert show_rate.resolve_template_id(key, appt, kind="no_show") is None, key
    # an older offer's booking still resolves
    old = dict(appt, campaign_id=settings.CAMPAIGNS["cleaning_reactivation"]["id"])
    assert show_rate.resolve_template_id("confirm_email", old)


def test_the_pricing_confirmed_time_version_says_the_call(index):
    v = [x for x in index["first_reply.ai_agents.pricing.full"]["variants"] if x["name"] == "confirmed_time"][0]
    assert "I will send the invite over. I'll have the exact number for you by the end of the call." in v["text"]
