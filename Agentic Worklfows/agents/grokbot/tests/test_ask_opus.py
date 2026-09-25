"""Offline tests for onboarding/ask_opus.py. The HTTP layer is mocked: no real call.

Run from Agentic Worklfows/:
    python3 -m pytest agents/grokbot/tests -q -p no:cacheprovider
"""

import importlib.util
import io
import json
import os
import shutil
import tempfile
import unittest
import urllib.error
from email.message import Message
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "onboarding", "ask_opus.py")
FIXTURE_DOC = os.path.join(HERE, "fixtures", "copy_doc_sample.txt")
REAL_DOC = os.path.join(HERE, "..", "..", "..", "tools", "template_doc", "exports",
                        "2026-09-25T0045Z_build_170b09dd897430a9.txt")
FAKE_KEY = "test-key-not-real-0000"

_spec = importlib.util.spec_from_file_location("ask_opus", SCRIPT)
ask_opus = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ask_opus)

E1_TEXT = ("Hey {first_name},\n\n\nThe time slots I sent got filled. Here are 2 more, "
           "let me know if they work: {slots}.\n\n\nLorenzo")
E2_TEXT = ("Hey {first_name},\n\n\n{research_line}\n\n\nFifteen minutes is enough for me to "
           "show you how this would run for {company}. Let me know when a good time is to "
           "get a call on the books.\n\n\nLorenzo")
E4_TEXT = ("Hey {first_name},\n\n\nI really think there's a lot of room for growth at {company}. "
           "I've built these systems across numerous industries. A few of my favorites:\n\n\n"
           "- {offer_proof}\n"
           "- an outbound system that raised a software consultancy's qualified lead volume 35%\n"
           "- $5M in loan applications in 30 days on $1,500 of ad spend for a lender\n\n\n"
           "The first one is the same kind of system I'd build for {company}. Those last two "
           "times got booked. Would {slots} work to go over it?\n\n\nLorenzo")
PROOF_REACTIVATION = ("a win-back system for a commercial roofer doing $150M a year that "
                      "recovered about $6M worth of contracts within 6 months")
PROOF_OUTBOUND = ("an outbound system for a commercial roofer doing $150M a year that brought "
                  "in about $180,000 in new contracts in 90 days")
GUARANTEE_LINE = ("I'm so confident that I guarantee at least $24,000 a year in new cleaning "
                  "contracts signed within 90 days, or I give your money back and throw in a "
                  "$200 gift card to your favorite steakhouse.")
FIRST_REPLY_LINE = ("Glad to hear it. All I need to start is a list of 60 or more lost or "
                    "dormant accounts or lost proposals.")
APPROVED = {"doc_done": True, "doc_unchanged": True, "go_live": True}


def decision(**overrides):
    base = {
        "action": "send_template", "category": None, "template_id": "cadence.e1",
        "template_text": E1_TEXT,
        "fields": [{"name": "first_name", "value": "Dana"},
                   {"name": "slots", "value": "Tue 12:05pm or Thu 4:30pm CT"}],
        "send_after": None, "ghl_stage": "no_change",
        "field_updates": [{"name": "Last Email Sent", "value": "cadence.e1"}],
        "instantly_interest": None, "other_actions": [], "draft_text": None,
        "escalate_to_lorenzo": False, "reason": "E1 is due today at 10:00 CT.",
        "confidence": 0.93,
    }
    base.update(overrides)
    return base


def api_payload(dec, stop_reason="end_turn"):
    return {
        "id": "msg_test", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
        "stop_reason": stop_reason,
        "content": [{"type": "thinking", "thinking": "", "signature": "sig"},
                    {"type": "text", "text": json.dumps(dec)}],
        "usage": {"input_tokens": 3000, "output_tokens": 2000,
                  "cache_read_input_tokens": 15000, "cache_creation_input_tokens": 0},
    }


class FakeResponse(object):
    def __init__(self, payload):
        self._body = json.dumps(payload).encode("utf-8")
        self.headers = {"request-id": "req_test"}

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def http_error(code, retry_after=None):
    headers = Message()
    if retry_after is not None:
        headers["retry-after"] = str(retry_after)
    return urllib.error.HTTPError(ask_opus.API_URL, code, "error", headers,
                                  io.BytesIO(b'{"type":"error"}'))


def case(**overrides):
    base = {
        "case_type": "followup_due",
        "question": "Is a follow-up due for this lead, and which one?",
        "context": {"approval": dict(APPROVED), "now_ct": "2026-09-28T10:00:00-05:00"},
        "copy_doc_file": FIXTURE_DOC,
    }
    base.update(overrides)
    return base


def run_main(case_obj, argv=None, env_key=FAKE_KEY):
    out = io.StringIO()
    env = {"ANTHROPIC_API_KEY": env_key} if env_key else {}
    with mock.patch.dict(os.environ, env, clear=True):
        code = ask_opus.main(argv or [], io.StringIO(json.dumps(case_obj)), out)
    return code, json.loads(out.getvalue()), out.getvalue()


class RequestShape(unittest.TestCase):
    def test_request_follows_opus_5_5_rules(self):
        body = ask_opus.build_request(case())
        self.assertEqual(body["model"], "claude-opus-5-5")
        self.assertEqual(body["max_tokens"], 16000)
        self.assertEqual(body["output_config"]["effort"], "medium")
        self.assertEqual(body["output_config"]["format"]["type"], "json_schema")
        for banned in ("temperature", "top_p", "top_k", "thinking", "tool_choice"):
            self.assertNotIn(banned, body)
        self.assertEqual(body["system"][-1]["cache_control"], {"type": "ephemeral"})
        self.assertIn("RULES YOU NEVER BREAK", body["system"][0]["text"])
        self.assertIn("(tag: cadence.e1)", body["system"][0]["text"])
        self.assertIn("<context>", body["messages"][0]["content"])

    def test_schema_objects_are_closed_and_fully_required(self):
        def walk(node):
            if isinstance(node, dict):
                if node.get("type") == "object":
                    self.assertIs(node.get("additionalProperties"), False)
                    self.assertEqual(sorted(node["required"]), sorted(node["properties"]))
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for value in node:
                    walk(value)
        walk(ask_opus.DECISION_SCHEMA)

    def test_headers_and_key_only_in_header(self):
        seen = {}

        def fake_urlopen(request, timeout=None):
            seen["headers"] = {k.lower(): v for k, v in request.header_items()}
            seen["data"] = request.data.decode("utf-8")
            seen["timeout"] = timeout
            return FakeResponse(api_payload(decision()))

        with mock.patch.object(ask_opus.urllib.request, "urlopen", side_effect=fake_urlopen):
            code, result, raw = run_main(case())
        self.assertEqual(code, 0)
        self.assertEqual(seen["headers"]["x-api-key"], FAKE_KEY)
        self.assertEqual(seen["headers"]["anthropic-version"], "2023-06-01")
        self.assertEqual(seen["headers"]["content-type"], "application/json")
        self.assertNotIn(FAKE_KEY, seen["data"])
        self.assertNotIn(FAKE_KEY, raw)
        self.assertEqual(seen["timeout"], ask_opus.TIMEOUT_SECONDS)

    def test_template_prefixes_filter_the_doc(self):
        body = ask_opus.build_request(case(template_prefixes=["booking.counter.weekend"]))
        text = body["system"][0]["text"]
        self.assertIn("(tag: booking.counter.weekend)", text)
        self.assertIn("(tag: formats.1)", text)
        self.assertNotIn("(tag: cadence.e1)", text)

    def test_prefix_with_no_match_is_refused(self):
        code, result, _ = run_main(case(template_prefixes=["nothing.here"]))
        self.assertEqual(code, 2)
        self.assertEqual(result["grok_next_step"], "hold_card")

    def test_bad_effort_is_refused(self):
        with self.assertRaises(ask_opus.InputError):
            ask_opus.build_request(case(effort="max"))


class Decisions(unittest.TestCase):
    def _run(self, dec, case_obj=None):
        with mock.patch.object(ask_opus.urllib.request, "urlopen",
                               return_value=FakeResponse(api_payload(dec))):
            return run_main(case_obj or case())

    def test_approved_template_renders_and_sends(self):
        code, result, _ = self._run(decision())
        self.assertEqual(code, 0)
        self.assertEqual(result["grok_next_step"], "send")
        self.assertEqual(result["email_text"],
                         "Hey Dana,\n\nThe time slots I sent got filled. Here are 2 more, "
                         "let me know if they work: Tue 12:05pm or Thu 4:30pm CT.\n\nLorenzo")
        self.assertTrue(all(result["checks"][k] for k in
                            ("copy_doc_checked", "template_found", "lines_match_template",
                             "no_leftover_placeholders", "field_values_clean", "approval_ok")))
        self.assertEqual(result["request_id"], "req_test")
        # 3000*4 + 2000*20 + 15000*0.2 = 55000 -> $0.055
        self.assertAlmostEqual(result["cost_usd"], 0.055)

    def test_low_confidence_holds(self):
        _, result, _ = self._run(decision(confidence=0.79))
        self.assertEqual(result["grok_next_step"], "hold_card")

    def test_escalate_holds(self):
        _, result, _ = self._run(decision(escalate_to_lorenzo=True))
        self.assertEqual(result["grok_next_step"], "hold_card")

    def test_invented_line_holds(self):
        text = E1_TEXT.replace("Here are 2 more", "Here are two fresh ones")
        _, result, _ = self._run(decision(template_text=text))
        self.assertEqual(result["grok_next_step"], "hold_card")
        self.assertFalse(result["checks"]["lines_match_template"])

    def test_lines_from_another_template_hold(self):
        text = E1_TEXT.replace(
            "The time slots I sent got filled. Here are 2 more, let me know if they work: {slots}.",
            "I really want to get this call on the books with you. Those last two times got taken too.")
        _, result, _ = self._run(decision(template_text=text))
        self.assertEqual(result["grok_next_step"], "hold_card")

    def test_unfilled_placeholder_holds(self):
        _, result, _ = self._run(decision(fields=[{"name": "first_name", "value": "Dana"}]))
        self.assertEqual(result["grok_next_step"], "hold_card")
        self.assertFalse(result["checks"]["no_leftover_placeholders"])

    def test_price_in_a_field_holds(self):
        fields = [{"name": "first_name", "value": "Dana"},
                  {"name": "slots", "value": "Tue 12:05pm CT, only $500"}]
        _, result, _ = self._run(decision(fields=fields))
        self.assertEqual(result["grok_next_step"], "hold_card")
        self.assertFalse(result["checks"]["field_values_clean"])

    def test_link_in_a_field_holds(self):
        fields = [{"name": "first_name", "value": "Dana"},
                  {"name": "slots", "value": "see https://example.com"}]
        _, result, _ = self._run(decision(fields=fields))
        self.assertEqual(result["grok_next_step"], "hold_card")

    def test_approved_fragment_line_is_allowed_in_a_field(self):
        fields = [{"name": "first_name", "value": "Dana"},
                  {"name": "company", "value": "Brightline"},
                  {"name": "research_line", "value": "The quickest place to start is usually "
                   "the accounts that already know you and went quiet."}]
        c = case(context={"approval": dict(APPROVED),
                          "lead": {"campaign_key": "cleaning_reactivation"}})
        _, result, _ = self._run(decision(template_id="cadence.e2", template_text=E2_TEXT,
                                          fields=fields), c)
        self.assertEqual(result["grok_next_step"], "send")
        # the same line with no campaign_key: the offer cannot be checked, so it holds
        _, result, _ = self._run(decision(template_id="cadence.e2", template_text=E2_TEXT,
                                          fields=fields))
        self.assertEqual(result["grok_next_step"], "hold_card")
        self.assertFalse(result["checks"]["field_values_clean"])

    def test_variant_line_matches_its_base_template(self):
        text = ("Hey {first_name},\n\n\n{asked_time} lands on a weekend for me. Could you send me "
                "a couple of times that work for you next week?\n\n\nLorenzo")
        fields = [{"name": "first_name", "value": "Dana"},
                  {"name": "asked_time", "value": "Sat 10:00am ET"}]
        _, result, _ = self._run(decision(template_id="booking.counter.weekend/no_alternatives",
                                          template_text=text, fields=fields))
        self.assertTrue(result["checks"]["lines_match_template"])
        self.assertEqual(result["grok_next_step"], "send")

    def test_first_reply_never_sends(self):
        text = ("Hey {first_name},\n\n\nGlad to hear it. All I need to start is a list of 60 or "
                "more lost or dormant accounts or lost proposals.\n\n\nLorenzo")
        _, result, _ = self._run(decision(
            template_id="first_reply.cleaning_reactivation.default.full",
            template_text=text, fields=[{"name": "first_name", "value": "Dana"}]))
        self.assertEqual(result["grok_next_step"], "hold_card")
        self.assertFalse(result["checks"]["approval_ok"])

    def test_cold_campaign_template_never_sends(self):
        _, result, _ = self._run(decision(template_id="instantly.cleaning_reactivation.step1",
                                          template_text="Let me know.", fields=[]))
        self.assertEqual(result["grok_next_step"], "hold_card")

    def test_doc_not_done_holds(self):
        c = case(context={"approval": {"doc_done": False, "doc_unchanged": True,
                                       "go_live": True}})
        _, result, _ = self._run(decision(), c)
        self.assertEqual(result["grok_next_step"], "hold_card")

    def test_doc_changed_or_not_live_holds(self):
        for approval in ({"doc_done": True, "doc_unchanged": False, "go_live": True},
                         {"doc_done": True, "doc_unchanged": True, "go_live": False},
                         {}):
            _, result, _ = self._run(decision(), case(context={"approval": approval}))
            self.assertEqual(result["grok_next_step"], "hold_card")
            self.assertFalse(result["checks"]["approval_ok"])

    def test_missing_copy_doc_holds(self):
        c = case()
        del c["copy_doc_file"]
        _, result, _ = self._run(decision(), c)
        self.assertEqual(result["grok_next_step"], "hold_card")
        self.assertFalse(result["checks"]["copy_doc_checked"])

    def test_hold_for_lorenzo_still_shows_the_rendered_email(self):
        _, result, _ = self._run(decision(action="hold_for_lorenzo"))
        self.assertEqual(result["grok_next_step"], "hold_card")
        self.assertTrue(result["email_text"].startswith("Hey Dana,"))

    def test_upwork_draft_goes_to_lorenzo(self):
        dec = decision(action="draft_for_lorenzo", template_id=None, template_text=None,
                       fields=[], draft_text="Hey Dana, one idea on the estimates.")
        _, result, _ = self._run(dec)
        self.assertEqual(result["grok_next_step"], "draft_to_lorenzo")
        self.assertIsNone(result["email_text"])

    def test_records_only_and_wait(self):
        rec = decision(action="records_only", template_id=None, template_text=None, fields=[],
                       ghl_stage="lost", instantly_interest=-1,
                       other_actions=["blocklist_in_instantly", "tag_dnd_in_ghl"])
        _, result, _ = self._run(rec)
        self.assertEqual(result["grok_next_step"], "update_records")
        wait = decision(action="wait", template_id=None, template_text=None, fields=[],
                        send_after="2026-09-29T10:00:00-05:00")
        _, result, _ = self._run(wait)
        self.assertEqual(result["grok_next_step"], "wait")

    def test_low_confidence_records_only_holds(self):
        rec = decision(action="records_only", template_id=None, template_text=None, fields=[],
                       confidence=0.6)
        _, result, _ = self._run(rec)
        self.assertEqual(result["grok_next_step"], "hold_card")


class RealDocFieldLines(unittest.TestCase):
    """Field values against the real export of build 170b09dd897430a9."""

    def _run(self, template_id, template_text, fields, campaign_key):
        c = case(copy_doc_file=REAL_DOC,
                 context={"approval": dict(APPROVED),
                          "lead": {"campaign_key": campaign_key}})
        dec = decision(template_id=template_id, template_text=template_text, fields=fields)
        with mock.patch.object(ask_opus.urllib.request, "urlopen",
                               return_value=FakeResponse(api_payload(dec))):
            return run_main(c)[1]

    def _e4(self, proof, campaign_key):
        fields = [{"name": "first_name", "value": "Dana"},
                  {"name": "company", "value": "Brightline Cleaning"},
                  {"name": "offer_proof", "value": proof},
                  {"name": "slots", "value": "Tue 12:05pm or Thu 4:30pm CT"}]
        return self._run("cadence.e4", E4_TEXT, fields, campaign_key)

    def test_e4_with_the_proof_line_for_the_lead_offer_sends(self):
        result = self._e4(PROOF_REACTIVATION, "cleaning_reactivation")
        self.assertEqual(result["grok_next_step"], "send", result["hold_reasons"])
        self.assertIn("- " + PROOF_REACTIVATION + "\n", result["email_text"])
        result = self._e4(PROOF_OUTBOUND, "cleaning_trigger")
        self.assertEqual(result["grok_next_step"], "send", result["hold_reasons"])

    def test_e4_with_the_other_offer_proof_line_holds(self):
        result = self._e4(PROOF_OUTBOUND, "cleaning_reactivation")
        self.assertEqual(result["grok_next_step"], "hold_card")
        self.assertFalse(result["checks"]["field_values_clean"])
        result = self._e4(PROOF_REACTIVATION, "recruiting_outbound")
        self.assertEqual(result["grok_next_step"], "hold_card")

    def test_e4_with_no_campaign_key_holds(self):
        result = self._e4(PROOF_REACTIVATION, None)
        self.assertEqual(result["grok_next_step"], "hold_card")

    def test_e4_with_the_guarantee_line_holds(self):
        result = self._e4(GUARANTEE_LINE, "cleaning_trigger")
        self.assertEqual(result["grok_next_step"], "hold_card")
        self.assertFalse(result["checks"]["field_values_clean"])

    def test_e2_with_a_first_reply_line_holds(self):
        fields = [{"name": "first_name", "value": "Dana"},
                  {"name": "company", "value": "Brightline Cleaning"},
                  {"name": "research_line", "value": FIRST_REPLY_LINE}]
        result = self._run("cadence.e2", E2_TEXT, fields, "cleaning_reactivation")
        self.assertEqual(result["grok_next_step"], "hold_card")
        self.assertIn("first_reply.cleaning_reactivation.default.full",
                      " ".join(result["checks"]["problems"]))

    def test_e2_with_an_instruction_line_holds(self):
        line = ("2. Nothing goes live until you tell Claude \"go live\".")
        fields = [{"name": "first_name", "value": "Dana"},
                  {"name": "company", "value": "Brightline Cleaning"},
                  {"name": "research_line", "value": line}]
        result = self._run("cadence.e2", E2_TEXT, fields, "cleaning_reactivation")
        self.assertEqual(result["grok_next_step"], "hold_card")

    def test_offer_suffixes(self):
        self.assertEqual(ask_opus.offer_suffixes({"lead": {"campaign_key": "cleaning_trigger"}}),
                         ["outbound_cleaning", "cleaning_outbound", "cleaning_trigger", "outbound"])
        self.assertEqual(ask_opus.offer_suffixes({"lead": {}}), [])
        with open(REAL_DOC, encoding="utf-8-sig") as handle:
            doc = handle.read()
        bookkeeping = {"lead": {"campaign_key": "bookkeeping_reactivation"}}
        allowed = ask_opus.allowed_fragment_lines(doc, "cadence.e5", bookkeeping)
        self.assertEqual(allowed, {"win back {company}'s past clients"})


class Spacing(unittest.TestCase):
    def test_export_double_blank_lines_become_one(self):
        text = ask_opus.render("Hey {a},  \n\n\n\nLine two.\n\n\nLorenzo\n",
                               [{"name": "a", "value": "Dana"}])
        self.assertEqual(text, "Hey Dana,\n\nLine two.\n\nLorenzo")

    def test_single_line_breaks_are_kept(self):
        text = ask_opus.render("Talk in an hour. Here's the link:\n{call_link}\n\nLorenzo",
                               [{"name": "call_link", "value": "https://meet.google.com/abc"}])
        self.assertEqual(text, "Talk in an hour. Here's the link:\nhttps://meet.google.com/abc"
                               "\n\nLorenzo")


class Failures(unittest.TestCase):
    def test_429_then_success_retries_and_honours_retry_after(self):
        calls = [http_error(429, retry_after=7), FakeResponse(api_payload(decision()))]

        def fake(request, timeout=None):
            item = calls.pop(0)
            if isinstance(item, Exception):
                raise item
            return item

        with mock.patch.object(ask_opus.urllib.request, "urlopen", side_effect=fake), \
                mock.patch.object(ask_opus.time, "sleep") as sleep:
            code, result, _ = run_main(case())
        self.assertEqual(code, 0)
        self.assertEqual(result["grok_next_step"], "send")
        sleep.assert_called_once_with(7.0)

    def test_5xx_every_time_gives_up_after_two_attempts(self):
        with mock.patch.object(ask_opus.urllib.request, "urlopen",
                               side_effect=http_error(529, retry_after=600)) as urlopen, \
                mock.patch.object(ask_opus.time, "sleep") as sleep:
            code, result, _ = run_main(case())
        self.assertEqual(code, 3)
        self.assertEqual(urlopen.call_count, 2)
        self.assertEqual(result["grok_next_step"], "hold_card")
        self.assertIsNone(result["model"])
        waited = sum(call[0][0] for call in sleep.call_args_list)
        worst = ask_opus.MAX_ATTEMPTS * ask_opus.TIMEOUT_SECONDS + waited
        self.assertLessEqual(worst, 300)

    def test_unreadable_skill_or_doc_file_is_a_hold_card(self):
        tmp = tempfile.mkdtemp()
        try:
            bad = os.path.join(tmp, "bad.md")
            with open(bad, "wb") as handle:
                handle.write(b"\xff\xfe\xfa not utf-8 \x80")
            for c in (case(skill_files=[bad]), case(skill_files=[os.path.join(tmp, "none.md")]),
                      case(copy_doc_file=bad), case(copy_doc_file=os.path.join(tmp, "none.txt"))):
                with mock.patch.object(ask_opus.urllib.request, "urlopen") as urlopen:
                    code, result, _ = run_main(c)
                self.assertEqual(code, 2)
                self.assertEqual(result["grok_next_step"], "hold_card")
                urlopen.assert_not_called()
        finally:
            shutil.rmtree(tmp)

    def test_model_comes_from_the_response(self):
        payload = api_payload(decision())
        payload["model"] = "claude-opus-5-5-from-response"
        with mock.patch.object(ask_opus.urllib.request, "urlopen",
                               return_value=FakeResponse(payload)):
            _, result, _ = run_main(case())
        self.assertEqual(result["model"], "claude-opus-5-5-from-response")
        self.assertEqual(result["model_requested"], "claude-opus-5-5")

    def test_network_error_is_retried(self):
        calls = [urllib.error.URLError("reset"), FakeResponse(api_payload(decision()))]

        def fake(request, timeout=None):
            item = calls.pop(0)
            if isinstance(item, Exception):
                raise item
            return item

        with mock.patch.object(ask_opus.urllib.request, "urlopen", side_effect=fake), \
                mock.patch.object(ask_opus.time, "sleep"):
            code, _, _ = run_main(case())
        self.assertEqual(code, 0)

    def test_400_is_not_retried(self):
        with mock.patch.object(ask_opus.urllib.request, "urlopen",
                               side_effect=http_error(400)) as urlopen, \
                mock.patch.object(ask_opus.time, "sleep"):
            code, result, _ = run_main(case())
        self.assertEqual(code, 3)
        self.assertEqual(urlopen.call_count, 1)
        self.assertEqual(result["grok_next_step"], "hold_card")

    def test_refusal_and_cutoff_hold(self):
        for stop in ("refusal", "max_tokens"):
            with mock.patch.object(ask_opus.urllib.request, "urlopen",
                                   return_value=FakeResponse(api_payload(decision(), stop))):
                code, result, _ = run_main(case())
            self.assertEqual(code, 3)
            self.assertEqual(result["grok_next_step"], "hold_card")

    def test_text_that_is_not_json_holds(self):
        payload = api_payload(decision())
        payload["content"][1]["text"] = "sure, here you go"
        with mock.patch.object(ask_opus.urllib.request, "urlopen",
                               return_value=FakeResponse(payload)):
            code, result, _ = run_main(case())
        self.assertEqual(code, 3)

    def test_missing_key_makes_no_call(self):
        with mock.patch.object(ask_opus.urllib.request, "urlopen") as urlopen:
            code, result, _ = run_main(case(), env_key=None)
        self.assertEqual(code, 2)
        urlopen.assert_not_called()
        self.assertIn("ANTHROPIC_API_KEY", result["hold_reasons"][0])

    def test_dry_run_makes_no_call_and_needs_no_key(self):
        with mock.patch.object(ask_opus.urllib.request, "urlopen") as urlopen:
            code, result, _ = run_main(case(), argv=["--dry-run"], env_key=None)
        self.assertEqual(code, 0)
        urlopen.assert_not_called()
        self.assertEqual(result["request"]["model"], "claude-opus-5-5")

    def test_bad_json_input(self):
        out = io.StringIO()
        code = ask_opus.main([], io.StringIO("{not json"), out)
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out.getvalue())["grok_next_step"], "hold_card")

    def test_relative_paths_resolve_next_to_the_script(self):
        tmp = tempfile.mkdtemp()
        try:
            shutil.copy(SCRIPT, os.path.join(tmp, "ask_opus.py"))
            os.mkdir(os.path.join(tmp, "skills"))
            with open(os.path.join(tmp, "skills", "x.md"), "w") as handle:
                handle.write("SKILL MARKER")
            spec = importlib.util.spec_from_file_location("ask_opus_copy",
                                                          os.path.join(tmp, "ask_opus.py"))
            copy = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(copy)
            body = copy.build_request({"question": "q", "context": {},
                                       "skill_files": ["skills/x.md"]})
            self.assertIn("SKILL MARKER", body["system"][0]["text"])
        finally:
            shutil.rmtree(tmp)


if __name__ == "__main__":
    unittest.main()
