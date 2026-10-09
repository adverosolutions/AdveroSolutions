"""n8n build quality: shorthand translation, real endpoints, overview and config.

These guard what a client sees when the workflow is opened on camera: nodes
that carry real prompts, channels, documents and endpoints instead of hollow
placeholders, and no shorthand key leaking into the file as an unknown param.

    python3 -m pytest -q tests/test_n8n_quality.py
"""

from __future__ import annotations

import copy
import json
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from upwork_gen.compile_n8n import (_sentence_case, compile_n8n, first_trigger,  # noqa: E402
                                    overview_markdown, overview_words, with_config_node)
from upwork_gen.generate import available_archetypes, load_archetype  # noqa: E402
from upwork_gen.layout import check, layout, text_height  # noqa: E402
from upwork_gen.params import (CONFIG_NODE_NAME, DEFAULT_PARSER_EXAMPLE,  # noqa: E402
                               SHORTHAND_CONDITION_OPS, SHORTHAND_KEYS, ascii_safe_obj,
                               config_keys_read, load_services, node_ref)
from upwork_gen.spec import Edge, WorkflowSpec, unique_names  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARCHETYPE_IDS = available_archetypes()

INPUT = {"name": "Ayesha Khan", "email": "ayesha@example.org", "phone": "0300 1234567",
         "company": "Khan Cleaning", "message": "Need a deep clean before Friday",
         "score": 82, "source": "Website"}
OUTPUT = {
    "duplicate": False,
    "qualification": {"service": "deep clean", "class": "hot",
                      "summary": "Wants a deep clean before Friday.",
                      "missing_fields": ["address"]},
    "log_row": {"run_id": "exec_1", "email": "ayesha@example.org", "class": "hot",
                "result": "success"},
}


def _base(nodes, edges, **extra):
    spec = {
        "title": "Quality Test Build",
        "platform": "n8n",
        "sections": [
            {"key": "in", "label": "1 - CAPTURE", "note": "Every enquiry lands here first."},
            {"key": "ai", "label": "2 - QUALIFY WITH AI", "note": "Claude reads the enquiry "
             "and classifies it. Nothing is invented."},
            {"key": "out", "label": "3 - NOTIFY AND LOG", "note": "Sales hears about it."},
        ],
        "nodes": nodes,
        "edges": edges,
        "input_sample": dict(INPUT),
        "output_sample": copy.deepcopy(OUTPUT),
    }
    spec.update(extra)
    return WorkflowSpec.from_dict(spec)


def _compile(spec):
    spec.validate()
    return compile_n8n(spec)


def _node(workflow, name_prefix):
    for node in workflow["nodes"]:
        if node["name"].startswith(name_prefix):
            return node
    raise AssertionError("no node named {!r}".format(name_prefix))


def _single(kind, params=None, app=None, label="2 - Step", extra_nodes=None, **extra):
    """A trigger followed by one node under test."""
    node = {"key": "x", "kind": kind, "label": label, "section": "ai"}
    if app:
        node["app"] = app
    if params is not None:
        node["params"] = params
    nodes = [{"key": "hook", "kind": "trigger.webhook", "label": "1 - Enquiry Arrives",
              "section": "in"}, node] + list(extra_nodes or [])
    return _base(nodes, [{"from": "hook", "to": "x"}], **extra)


class TestConditionShorthand(unittest.TestCase):
    def test_branch_condition(self):
        spec = _single("flow.branch", {"condition": {"left": "={{ $json.score }}",
                                                    "op": "gte", "right": 70}},
                       label="2 - Hot Enough?")
        params = _node(_compile(spec), "2 - Hot Enough")["parameters"]
        self.assertNotIn("condition", params)
        cond = params["conditions"]["conditions"][0]
        self.assertEqual(cond["leftValue"], "={{ $json.score }}")
        self.assertEqual(cond["rightValue"], 70)
        self.assertEqual(cond["operator"], {"type": "number", "operation": "gte"})

    def test_every_op_translates(self):
        expected = {"gte": ("number", "gte"), "gt": ("number", "gt"),
                    "lte": ("number", "lte"), "lt": ("number", "lt"),
                    "eq": ("string", "equals"), "neq": ("string", "notEquals"),
                    "contains": ("string", "contains"), "exists": ("string", "exists"),
                    "true": ("boolean", "true"), "false": ("boolean", "false")}
        self.assertEqual(set(expected), set(SHORTHAND_CONDITION_OPS))
        for op, (kind, operation) in expected.items():
            with self.subTest(op=op):
                right = 5 if kind == "number" else "hot"
                spec = _single("flow.branch", {"condition": {"left": "$json.class", "op": op,
                                                            "right": right}},
                               label="2 - Gate?")
                cond = _node(_compile(spec), "2 - Gate")["parameters"]["conditions"][
                    "conditions"][0]
                self.assertEqual(cond["leftValue"], "={{ $json.class }}")
                self.assertEqual(cond["operator"]["type"], kind)
                self.assertEqual(cond["operator"]["operation"], operation)
                if op in ("exists", "true", "false"):
                    self.assertTrue(cond["operator"].get("singleValue"))
                    self.assertEqual(cond["rightValue"], "")

    def test_filter_condition(self):
        spec = _single("data.filter", {"condition": {"left": "email", "op": "contains",
                                                    "right": "@"}},
                       label="2 - Keep Real Emails")
        params = _node(_compile(spec), "2 - Keep Real Emails")["parameters"]
        self.assertNotIn("condition", params)
        cond = params["conditions"]["conditions"][0]
        self.assertEqual(cond["leftValue"], "={{ $json.email }}")
        self.assertEqual(cond["operator"]["operation"], "contains")

    def test_default_condition_uses_real_fields(self):
        spec = _single("flow.branch", None, label="2 - Required Fields Present?")
        conds = _node(_compile(spec), "2 - Required")["parameters"]["conditions"]["conditions"]
        lefts = [c["leftValue"] for c in conds]
        self.assertIn("={{ $json.email }}", lefts)
        self.assertTrue(all(c["operator"]["operation"] == "notEmpty" for c in conds))


class TestAiShorthand(unittest.TestCase):
    def test_llm_prompt_and_system_message(self):
        spec = _single("ai.llm", {"prompt": "Classify {{ $json.message }}",
                                  "system_message": "You sort enquiries."},
                       label="2 - Classify",
                       extra_nodes=[{"key": "m", "kind": "ai.model", "app": "anthropic",
                                     "label": "Claude", "parent": "x"}])
        params = _node(_compile(spec), "2 - Classify")["parameters"]
        self.assertEqual(params["promptType"], "define")
        self.assertEqual(params["text"], "=Classify {{ $json.message }}")
        self.assertEqual(params["messages"]["messageValues"][0]["message"],
                         "You sort enquiries.")
        self.assertNotIn("prompt", params)
        self.assertNotIn("system_message", params)

    def test_agent_prompt_and_system_message(self):
        spec = _single("ai.agent", {"prompt": "Handle {{ $json.message }}",
                                    "system_message": "You book jobs."},
                       label="2 - Booking Agent",
                       extra_nodes=[{"key": "m", "kind": "ai.model", "app": "openai",
                                     "label": "OpenAI", "parent": "x"}])
        params = _node(_compile(spec), "2 - Booking Agent")["parameters"]
        self.assertEqual(params["promptType"], "define")
        self.assertEqual(params["text"], "=Handle {{ $json.message }}")
        self.assertEqual(params["options"]["systemMessage"], "You book jobs.")
        self.assertNotIn("system_message", params)
        self.assertNotIn("prompt", params)

    def test_agent_gets_a_synthesised_system_message(self):
        spec = _single("ai.agent", None, label="2 - Qualify the Enquiry",
                       extra_nodes=[{"key": "m", "kind": "ai.model", "app": "openai",
                                     "label": "OpenAI", "parent": "x"}],
                       client={"name": "Sam", "company": "Acme Cleaning"})
        params = _node(_compile(spec), "2 - Qualify the Enquiry")["parameters"]
        system = params["options"]["systemMessage"]
        self.assertIn("You work for Acme Cleaning.", system)
        self.assertIn("Claude reads the enquiry and classifies it.", system)
        self.assertIn("Your job in this step: Qualify the Enquiry.", system)
        self.assertEqual(params["promptType"], "define")
        self.assertIn("{{ $json.email }}", params["text"])
        self.assertNotEqual(params["text"].lstrip("=").strip(), "2 - Qualify the Enquiry")

    def test_llm_default_prompt_is_not_the_label(self):
        spec = _single("ai.llm", None, label="2 - Summarize",
                       extra_nodes=[{"key": "m", "kind": "ai.model", "app": "anthropic",
                                     "label": "Claude", "parent": "x"}])
        params = _node(_compile(spec), "2 - Summarize")["parameters"]
        self.assertNotIn("2 - Summarize", params["text"])
        self.assertIn("{{ $json.message }}", params["text"])
        self.assertTrue(params["messages"]["messageValues"][0]["message"])

    def test_parser_schema_shorthand(self):
        schema = {"tier": "A", "reason": "text"}
        spec = _single("ai.llm", None, label="2 - Score",
                       extra_nodes=[{"key": "m", "kind": "ai.model", "app": "anthropic",
                                     "label": "Claude", "parent": "x"},
                                    {"key": "p", "kind": "ai.parser", "label": "Tier",
                                     "parent": "x", "params": {"schema": schema}}])
        params = _node(_compile(spec), "Tier")["parameters"]
        self.assertEqual(json.loads(params["jsonSchemaExample"]), schema)
        self.assertEqual(params["schemaType"], "fromJson")
        self.assertNotIn("schema", params)

    def test_parser_derived_from_output_sample(self):
        spec = _single("ai.llm", None, label="2 - Extract Service, Classify",
                       extra_nodes=[{"key": "m", "kind": "ai.model", "app": "anthropic",
                                     "label": "Claude", "parent": "x"},
                                    {"key": "p", "kind": "ai.parser",
                                     "label": "Service, Summary, Class, Missing Fields",
                                     "parent": "x"}])
        workflow = _compile(spec)
        example = json.loads(_node(workflow, "Service, Summary")["parameters"][
            "jsonSchemaExample"])
        self.assertEqual(example, OUTPUT["qualification"])
        self.assertNotEqual(example, DEFAULT_PARSER_EXAMPLE)
        # The chain is told to return exactly those fields.
        system = _node(workflow, "2 - Extract")["parameters"]["messages"]["messageValues"][0][
            "message"]
        self.assertIn("service, class, summary, missing_fields", system)

    def test_parser_with_input_schema_drops_default_example(self):
        schema = json.dumps({"type": "object", "properties": {"a": {"type": "string"}}})
        spec = _single("ai.llm", None, label="2 - Score",
                       extra_nodes=[{"key": "m", "kind": "ai.model", "app": "anthropic",
                                     "label": "Claude", "parent": "x"},
                                    {"key": "p", "kind": "ai.parser", "label": "Schema",
                                     "parent": "x", "params": {"inputSchema": schema}}])
        params = _node(_compile(spec), "Schema")["parameters"]
        self.assertEqual(params["schemaType"], "manual")
        self.assertEqual(params["inputSchema"], schema)
        self.assertNotIn("jsonSchemaExample", params)


class TestAppShorthand(unittest.TestCase):
    def test_slack_channel_and_text(self):
        spec = _single("app.action", {"channel": "#new-leads", "text": "New lead {{ $json.name }}"},
                       app="slack", label="2 - Tell Sales")
        params = _node(_compile(spec), "2 - Tell Sales")["parameters"]
        self.assertEqual(params["channelId"], {"__rl": True, "mode": "name", "value": "#new-leads"})
        self.assertEqual(params["text"], "=New lead {{ $json.name }}")
        self.assertNotIn("channel", params)

    def test_slack_defaults(self):
        spec = _single("app.action", None, app="slack", label="2 - Alert the Team")
        params = _node(_compile(spec), "2 - Alert the Team")["parameters"]
        self.assertTrue(params["channelId"]["value"].startswith("#"))
        self.assertNotIn("reason_for_calling", params["text"])
        self.assertIn("Alert the Team", params["text"])
        self.assertGreaterEqual(params["text"].count("{{ $json."), 2)

    def test_sheets_document_sheet_columns(self):
        spec = _single("app.action", {"document": "1AbCdEfGh", "sheet": "Leads",
                                      "columns": ["Lead Name", "email"]},
                       app="googleSheets", label="2 - Log the Lead")
        params = _node(_compile(spec), "2 - Log the Lead")["parameters"]
        self.assertEqual(params["documentId"]["value"], "1AbCdEfGh")
        self.assertEqual(params["sheetName"], {"__rl": True, "mode": "name", "value": "Leads"})
        self.assertEqual(params["columns"]["mappingMode"], "defineBelow")
        self.assertEqual(params["columns"]["value"], {"Lead Name": "={{ $json.lead_name }}",
                                                      "email": "={{ $json.email }}"})
        self.assertNotIn("document", params)
        self.assertNotIn("sheet", params)

    def test_sheets_default_columns_from_sample(self):
        spec = _single("app.action", None, app="googleSheets", label="2 - Execution Log Row")
        params = _node(_compile(spec), "2 - Execution Log Row")["parameters"]
        self.assertTrue(params["documentId"]["value"])
        self.assertEqual(list(params["columns"]["value"]), list(OUTPUT["log_row"]))

    def test_airtable_document_sheet_columns(self):
        spec = _single("app.action", {"document": "appXYZ", "sheet": "Jobs",
                                      "columns": ["Job Id", "Status"]},
                       app="airtable", label="2 - Create Job Record")
        params = _node(_compile(spec), "2 - Create Job Record")["parameters"]
        self.assertEqual(params["base"]["value"], "appXYZ")
        self.assertEqual(params["table"]["value"], "Jobs")
        self.assertEqual(params["columns"]["value"]["Job Id"], "={{ $json.job_id }}")
        for key in ("document", "sheet"):
            self.assertNotIn(key, params)


class TestHttp(unittest.TestCase):
    def test_every_service_has_real_https_urls(self):
        for key, service in load_services().items():
            with self.subTest(service=key):
                self.assertTrue(service["operations"])
                self.assertIn(service.get("default_op"), service["operations"])
                blob = json.dumps(service)
                self.assertNotIn("example.com", blob)

    def test_service_shorthand(self):
        spec = _single("net.http", {"service": "instantly"}, label="2 - Add to Campaign")
        node = _node(_compile(spec), "2 - Add to Campaign")
        params = node["parameters"]
        self.assertEqual(params["url"], "https://api.instantly.ai/api/v2/leads")
        headers = {h["name"]: h["value"] for h in params["headerParameters"]["parameters"]}
        self.assertEqual(headers["Authorization"], "Bearer PASTE-YOUR-INSTANTLY-API-KEY")
        self.assertIn('"campaign": "PASTE-YOUR-INSTANTLY-CAMPAIGN-ID"', params["jsonBody"])
        self.assertNotIn("service", params)
        # Retries are node settings, not parameters.
        self.assertTrue(node.get("retryOnFail"))
        self.assertNotIn("retryOnFail", params)

    def test_method_url_headers_body_shorthand(self):
        spec = _single("net.http", {"method": "patch", "url": "https://api.acme.io/v2/jobs",
                                    "headers": {"X-Token": "YOUR_ACME_TOKEN"},
                                    "body": {"status": "booked"}},
                       label="2 - Mark Job Booked")
        params = _node(_compile(spec), "2 - Mark Job Booked")["parameters"]
        self.assertEqual(params["method"], "PATCH")
        self.assertEqual(params["url"], "https://api.acme.io/v2/jobs")
        self.assertEqual(params["headerParameters"]["parameters"],
                         [{"name": "X-Token", "value": "YOUR_ACME_TOKEN"}])
        self.assertEqual(json.loads(params["jsonBody"].lstrip("=")), {"status": "booked"})
        for key in ("headers", "body"):
            self.assertNotIn(key, params)

    def test_service_resolved_from_label(self):
        spec = _single("net.http", None, label="2 - GoHighLevel: Upsert Contact")
        params = _node(_compile(spec), "2 - GoHighLevel")["parameters"]
        self.assertEqual(params["url"], "https://services.leadconnectorhq.com/contacts/upsert")
        headers = {h["name"]: h["value"] for h in params["headerParameters"]["parameters"]}
        self.assertEqual(headers["Version"], "2021-07-28")
        self.assertEqual(headers["Authorization"], "Bearer PASTE-YOUR-GHL-API-KEY")

    def test_operation_picked_by_label(self):
        cases = {
            "2 - GHL: Tag by Class": "/tags",
            "2 - GHL: Create the Opportunity": "/opportunities/",
            "2 - GHL: Remove From the Follow-Up Workflow": "/workflow/",
            "2 - Hunter: Verify the Email": "/email-verifier",
            "2 - Apollo: Enrich the Person": "/people/match",
            "2 - Firecrawl: Scrape the Website": "/scrape",
        }
        for label, fragment in cases.items():
            with self.subTest(label=label):
                spec = _single("net.http", None, label=label)
                params = _node(_compile(spec), label)["parameters"]
                self.assertIn(fragment, params["url"])
        spec = _single("net.http", None, label="2 - GHL: Remove From the Follow-Up Workflow")
        self.assertEqual(_node(_compile(spec), "2 - GHL")["parameters"]["method"], "DELETE")

    def test_auth_reads_the_config_node(self):
        spec = _single("net.http", None, label="2 - GHL: Upsert Contact",
                       config={"ghl_location_id": "PASTE-YOUR-LOCATION"})
        workflow = _compile(spec)
        params = _node(workflow, "2 - GHL")["parameters"]
        headers = {h["name"]: h["value"] for h in params["headerParameters"]["parameters"]}
        self.assertEqual(headers["Authorization"],
                         "=Bearer {{ $('%s').item.json.ghl_api_key }}" % CONFIG_NODE_NAME)
        config = _node(workflow, CONFIG_NODE_NAME)["parameters"]
        names = [a["name"] for a in config["assignments"]["assignments"]]
        self.assertIn("ghl_location_id", names)
        self.assertIn("ghl_api_key", names)  # added because the HTTP node reads it

    def test_unmatched_keeps_an_obvious_placeholder(self):
        spec = _single("net.http", None, label="2 - Pull the Weekly Numbers")
        params = _node(_compile(spec), "2 - Pull the Weekly")["parameters"]
        self.assertIn("example.com", params["url"])


class TestWebhookPaths(unittest.TestCase):
    def test_paths_are_unique_and_readable(self):
        nodes = [
            {"key": "a", "kind": "trigger.webhook", "label": "1 - New Lead", "section": "in"},
            {"key": "b", "kind": "trigger.webhook", "label": "1 - New Lead", "section": "in"},
            {"key": "c", "kind": "trigger.webhook", "label": "5 - Replied", "section": "out"},
            {"key": "s", "kind": "data.transform", "label": "2 - Tidy", "section": "in"},
        ]
        edges = [{"from": "a", "to": "s"}, {"from": "b", "to": "s"}, {"from": "c", "to": "s"}]
        workflow = _compile(_base(nodes, edges))
        paths = [n["parameters"]["path"] for n in workflow["nodes"]
                 if n["type"] == "n8n-nodes-base.webhook"]
        self.assertEqual(len(paths), 3)
        self.assertEqual(len(set(paths)), 3)
        self.assertNotIn("incoming", paths)
        self.assertIn("lead", paths[0])

    def test_vault_webhook_paths_unique(self):
        for archetype_id in ARCHETYPE_IDS:
            with self.subTest(archetype=archetype_id):
                spec = load_archetype(archetype_id)
                workflow = compile_n8n(spec)
                paths = [n["parameters"].get("path") for n in workflow["nodes"]
                         if "webhook" in n["type"].lower() and "path" in n["parameters"]]
                self.assertEqual(len(paths), len(set(paths)))


class TestOverviewSticky(unittest.TestCase):
    def _flow(self, **extra):
        return _single("app.action", None, app="slack", label="2 - Tell Sales", **extra)

    def test_overview_with_client(self):
        spec = self._flow(client={"name": "Sam Lee", "company": "Acme Cleaning"},
                          overview={"need_from_you": ["Slack workspace access"]})
        workflow = _compile(spec)
        sticky = _node(workflow, "Overview")
        content = sticky["parameters"]["content"]
        self.assertTrue(content.startswith("## Quality Test Build"))
        self.assertIn("Built for Acme Cleaning", content)
        self.assertIn("### How it works", content)
        self.assertIn("### Setup", content)
        self.assertIn("### What I need from you", content)
        self.assertEqual(sticky["parameters"]["color"], 1)
        # Top-left: left of every other node, and no lower than any band's top.
        others = [n for n in workflow["nodes"] if n is not sticky]
        right_edge = sticky["position"][0] + sticky["parameters"]["width"]
        self.assertTrue(all(right_edge <= n["position"][0] for n in others))
        words = len(content.split())
        self.assertLessEqual(words, 320)

    def test_overview_without_client(self):
        workflow = _compile(self._flow())
        content = _node(workflow, "Overview")["parameters"]["content"]
        self.assertNotIn("Built for", content)
        self.assertIn("- Capture: Every enquiry lands here first.", content)
        self.assertIn("Slack", content)

    def test_overview_uses_spec_bullets(self):
        spec = self._flow(overview={"how_it_works": ["Leads arrive", "AI scores them"],
                                    "setup": ["Connect Slack"]})
        content = overview_markdown(spec)
        self.assertIn("- Leads arrive", content)
        self.assertIn("- Connect Slack", content)
        self.assertNotIn("Capture:", content)

    def test_overview_never_overlaps(self):
        for archetype_id in ARCHETYPE_IDS:
            with self.subTest(archetype=archetype_id):
                spec = with_config_node(load_archetype(archetype_id))
                placement = layout(spec, overview=overview_markdown(spec))
                self.assertIsNotNone(placement.overview)
                self.assertEqual(check(spec, placement), [])


class TestConfigNode(unittest.TestCase):
    def _spec(self, **extra):
        nodes = [
            {"key": "err", "kind": "trigger.app", "app": "n8n", "op": "error_trigger",
             "label": "9 - Any Step Fails", "section": "out"},
            {"key": "hook", "kind": "trigger.webhook", "label": "1 - Enquiry Arrives",
             "section": "in"},
            {"key": "tidy", "kind": "data.transform", "label": "2 - Tidy", "section": "in"},
            {"key": "stop", "kind": "trigger.webhook", "label": "5 - Replied", "section": "out"},
            {"key": "alert", "kind": "app.action", "app": "slack", "label": "10 - Alert",
             "section": "out"},
            {"key": "done", "kind": "flow.noop", "label": "6 - Done", "section": "out"},
        ]
        edges = [{"from": "hook", "to": "tidy"}, {"from": "stop", "to": "done"},
                 {"from": "err", "to": "alert"}]
        return _base(nodes, edges, **extra)

    def test_inserted_after_first_non_error_trigger(self):
        spec = self._spec(config={"slack_channel": "#new-leads",
                                  "sheet_id": "PASTE-YOUR-SHEET-ID"})
        self.assertEqual(first_trigger(spec).key, "hook")
        workflow = _compile(spec)
        conns = workflow["connections"]
        self.assertEqual(conns["1 - Enquiry Arrives"]["main"][0][0]["node"], CONFIG_NODE_NAME)
        self.assertEqual(conns[CONFIG_NODE_NAME]["main"][0][0]["node"], "2 - Tidy")
        self.assertEqual(conns["5 - Replied"]["main"][0][0]["node"], "6 - Done")
        self.assertEqual(conns["9 - Any Step Fails"]["main"][0][0]["node"], "10 - Alert")
        config = _node(workflow, CONFIG_NODE_NAME)
        self.assertEqual(config["type"], "n8n-nodes-base.set")
        assignments = config["parameters"]["assignments"]["assignments"]
        self.assertEqual({a["name"]: a["value"] for a in assignments},
                         {"slack_channel": "#new-leads", "sheet_id": "PASTE-YOUR-SHEET-ID"})
        self.assertTrue(config["parameters"]["includeOtherFields"])
        # Sample data is never pinned on the inserted node.
        self.assertNotIn(CONFIG_NODE_NAME, workflow["pinData"])

    def test_layout_clean_with_config(self):
        spec = with_config_node(self._spec(config={"api_key": "PASTE-YOUR-KEY"}))
        self.assertEqual(check(spec, layout(spec, overview=overview_markdown(spec))), [])

    def test_no_config_no_node(self):
        workflow = _compile(self._spec())
        self.assertFalse(any(n["name"] == CONFIG_NODE_NAME for n in workflow["nodes"]))


class TestStickyFit(unittest.TestCase):
    def test_long_note_grows_the_heading(self):
        long_note = ("Every enquiry is de-duplicated, standardized and checked against the CRM "
                     "before anything is created, so nothing is ever written twice and the "
                     "team sees one clean record. ") * 3
        spec = _single("data.transform", None, label="2 - Tidy")
        spec.sections[0].note = long_note
        placement = layout(spec)
        self.assertEqual(check(spec, placement), [])
        sticky = [s for s in placement.stickies if s.key == "in"][0]
        self.assertGreater(sticky.heading, 110)
        self.assertEqual(sticky.heading, text_height(sticky.content, sticky.width))
        first_y = placement.positions["hook"][1]
        self.assertGreaterEqual(first_y, sticky.y + sticky.heading)


class TestTransform(unittest.TestCase):
    def test_set_nodes_are_not_identical_copies(self):
        nodes = [
            {"key": "hook", "kind": "trigger.webhook", "label": "1 - In", "section": "in"},
            {"key": "a", "kind": "data.transform", "label": "2 - Normalize", "section": "in"},
            {"key": "b", "kind": "data.transform", "label": "3 - Standardize Email and Phone",
             "section": "in"},
            {"key": "c", "kind": "data.transform", "label": "4 - Build the Log Row",
             "section": "out"},
        ]
        edges = [{"from": "hook", "to": "a"}, {"from": "a", "to": "b"}, {"from": "b", "to": "c"}]
        workflow = _compile(_base(nodes, edges))
        shapes = []
        for name in ("2 - Normalize", "3 - Standardize", "4 - Build"):
            assignments = _node(workflow, name)["parameters"]["assignments"]["assignments"]
            shapes.append(json.dumps([(a["name"], a["value"]) for a in assignments]))
        self.assertEqual(len(set(shapes)), 3)
        std = _node(workflow, "3 - Standardize")["parameters"]["assignments"]["assignments"]
        email = [a for a in std if a["name"] == "email"][0]
        self.assertIn("toLowerCase", email["value"])


class TestSpecFields(unittest.TestCase):
    def test_round_trip(self):
        spec = _single("flow.noop", None, client={"name": "Sam", "company": "Acme",
                                                 "industry": "Cleaning", "location": "TX",
                                                 "ignored": "x"},
                       overview={"how_it_works": ["a"], "setup": "b"},
                       config={"api_key": "PASTE-YOUR-KEY"})
        data = spec.to_dict()
        self.assertEqual(data["client"], {"name": "Sam", "company": "Acme",
                                          "industry": "Cleaning", "location": "TX"})
        self.assertEqual(data["overview"], {"how_it_works": ["a"], "setup": ["b"]})
        self.assertEqual(data["config"], {"api_key": "PASTE-YOUR-KEY"})
        again = WorkflowSpec.from_dict(data)
        self.assertEqual(again.to_dict(), data)

    def test_old_specs_still_load(self):
        import glob
        paths = glob.glob(os.path.join(ROOT, "vault", "archetypes", "*.json")) + \
            glob.glob(os.path.join(ROOT, "examples", "*.json"))
        self.assertTrue(paths)
        for path in paths:
            with self.subTest(path=os.path.basename(path)):
                spec = WorkflowSpec.load(path)
                spec.validate()
                self.assertNotIn("client", spec.to_dict())


# Shorthand keys that are not also real n8n parameter names on that node type.
_LEAK_KEYS = {"condition", "prompt", "system_message", "schema", "service", "headers",
              "channel", "document", "sheet"}


class TestEveryArchetype(unittest.TestCase):
    def test_compiles_clean_with_no_dangling_connections(self):
        for archetype_id in ARCHETYPE_IDS:
            with self.subTest(archetype=archetype_id):
                spec = load_archetype(archetype_id)
                spec.validate()
                workflow = compile_n8n(spec)
                names = {n["name"] for n in workflow["nodes"]}
                self.assertEqual(len(names), len(workflow["nodes"]))
                for source, ports in workflow["connections"].items():
                    self.assertIn(source, names)
                    for groups in ports.values():
                        for group in groups:
                            for target in group:
                                self.assertIn(target["node"], names)
                for node in workflow["nodes"]:
                    leaked = _LEAK_KEYS & set(node["parameters"])
                    self.assertFalse(leaked, "{} leaks {}".format(node["name"], leaked))
                    if node["type"] == "@n8n/n8n-nodes-langchain.outputParserStructured" \
                            and spec.output_sample:
                        example = node["parameters"].get("jsonSchemaExample")
                        if example:
                            self.assertNotEqual(json.loads(example.lstrip("=")),
                                                DEFAULT_PARSER_EXAMPLE)

    def test_with_client_and_config_injected(self):
        for archetype_id in ARCHETYPE_IDS:
            with self.subTest(archetype=archetype_id):
                spec = load_archetype(archetype_id)
                spec.client = {"company": "Acme Co"}
                spec.config = {"api_key": "PASTE-YOUR-API-KEY"}
                workflow = compile_n8n(spec)
                names = {n["name"] for n in workflow["nodes"]}
                for ports in workflow["connections"].values():
                    for groups in ports.values():
                        for group in groups:
                            for target in group:
                                self.assertIn(target["node"], names)
                # Inserted with or without a trigger (defect 2).
                self.assertIn(CONFIG_NODE_NAME, names)
                self.assertIn("Built for Acme Co", _node(workflow, "Overview")["parameters"][
                    "content"])

    def test_no_reason_for_calling_leftover(self):
        """The old Slack default read `$json.reason_for_calling` in every build.
        The field may appear only where the archetype's own samples have it,
        and never in a synthesised Slack message."""
        for archetype_id in ARCHETYPE_IDS:
            with self.subTest(archetype=archetype_id):
                spec = load_archetype(archetype_id)
                workflow = compile_n8n(spec)
                own = "reason_for_calling" in json.dumps(
                    [spec.input_sample, spec.output_sample,
                     [n.params for n in spec.nodes]])
                for node in workflow["nodes"]:
                    text = json.dumps(node["parameters"])
                    if node["type"] == "n8n-nodes-base.slack" or not own:
                        self.assertNotIn("reason_for_calling", text, node["name"])

    def test_shorthand_table_is_documented(self):
        for kind, keys in SHORTHAND_KEYS.items():
            self.assertTrue(keys, kind)


# --------------------------------------------------------------------------
# Review round 2: defects 1-12 and the PASTE-YOUR- placeholder rule
# --------------------------------------------------------------------------

JOBS_DIR = os.path.join(os.path.dirname(ROOT), "upwork-pipeline", "jobs")
JOB_SPECS = ["n8n-ghl-lead-qualification-follow-ups", "crm-automation-multi-system-api-claude-n8n",
             "ai-automation-developer-openai-n8n"]


def _job_spec(slug):
    """A job's spec.json, read only (never written)."""
    path = os.path.join(JOBS_DIR, slug, "spec.json")
    if not os.path.exists(path):
        raise unittest.SkipTest("job folder {} not present".format(slug))
    return WorkflowSpec.load(path)


def _all_specs():
    """Every vault archetype plus the job specs that exist on this machine."""
    out = [(a, load_archetype(a)) for a in ARCHETYPE_IDS]
    for slug in JOB_SPECS:
        path = os.path.join(JOBS_DIR, slug, "spec.json")
        if os.path.exists(path):
            out.append((slug, WorkflowSpec.load(path)))
    return out


def _upstream(workflow, name):
    """Names of every node that runs before `name` in the same execution.
    A sub-node inherits its parent's upstream."""
    rev = {}
    parent = {}
    for src, ports in workflow["connections"].items():
        for port, groups in ports.items():
            for group in groups:
                for target in group:
                    if port == "main":
                        rev.setdefault(target["node"], set()).add(src)
                    else:
                        parent[src] = target["node"]
    start = name
    while start in parent:
        start = parent[start]
    seen, stack = set(), [start]
    while stack:
        current = stack.pop()
        for src in rev.get(current, ()):
            if src not in seen:
                seen.add(src)
                stack.append(src)
    return seen


_CONFIG_REF = re.compile(r"\$\('((?:[^'\\]|\\.)*Config: Your Settings(?:[^'\\]|\\.)*)'\)")


def _config_refs(workflow):
    """(node name, referenced Config node name) for every Config expression."""
    out = []
    for node in workflow["nodes"]:
        text = json.dumps(node["parameters"], ensure_ascii=False)
        for ref in set(_CONFIG_REF.findall(text)):
            out.append((node["name"], ref))
    return out


def _ghl(key, label, section="in", **extra):
    node = {"key": key, "kind": "net.http", "label": label, "section": section}
    node.update(extra)
    return node


class TestConfigOnEveryTriggerPath(unittest.TestCase):
    """Defect 1: a node reads a Config node only when that node is upstream."""

    def _multi(self):
        nodes = [
            {"key": "err", "kind": "trigger.app", "app": "n8n", "op": "error_trigger",
             "label": "9 - Any Step Fails", "section": "out"},
            {"key": "hook", "kind": "trigger.webhook", "label": "1 - Enquiry Arrives",
             "section": "in"},
            _ghl("upsert", "2 - GHL: Upsert Contact"),
            {"key": "stop", "kind": "trigger.webhook", "label": "5 - GHL: Replied or Booked",
             "section": "out"},
            _ghl("unenroll", "6 - GHL: Remove From the Follow-Up Workflow", "out"),
            _ghl("errtag", "10 - GHL: Tag the Contact as Errored", "out"),
            {"key": "alert", "kind": "app.action", "app": "slack", "label": "11 - Alert",
             "section": "out"},
            {"key": "quiet", "kind": "trigger.webhook", "label": "7 - Ping", "section": "out"},
            {"key": "noop", "kind": "flow.noop", "label": "8 - Done", "section": "out"},
        ]
        edges = [{"from": "hook", "to": "upsert"}, {"from": "stop", "to": "unenroll"},
                 {"from": "err", "to": "errtag"}, {"from": "errtag", "to": "alert"},
                 {"from": "quiet", "to": "noop"}]
        return _base(nodes, edges, config={"ghl_location_id": "PASTE-YOUR-LOCATION-ID"})

    def test_every_reference_has_its_config_upstream(self):
        workflow = _compile(self._multi())
        refs = _config_refs(workflow)
        self.assertTrue(refs)
        for name, ref in refs:
            with self.subTest(node=name, ref=ref):
                self.assertIn(ref.replace("\\'", "'"), _upstream(workflow, name))

    def test_one_config_node_other_paths_get_placeholders(self):
        workflow = _compile(self._multi())
        names = [n["name"] for n in workflow["nodes"]]
        self.assertEqual([n for n in names if "Config" in n], [CONFIG_NODE_NAME])
        conns = workflow["connections"]
        # Three business triggers that never join: after the first one.
        self.assertEqual(conns["1 - Enquiry Arrives"]["main"][0][0]["node"], CONFIG_NODE_NAME)
        self.assertEqual(conns["5 - GHL: Replied or Booked"]["main"][0][0]["node"],
                         "6 - GHL: Remove From the Follow-Up Workflow")
        self.assertEqual(conns["9 - Any Step Fails"]["main"][0][0]["node"],
                         "10 - GHL: Tag the Contact as Errored")
        self.assertIn("$('%s')" % CONFIG_NODE_NAME,
                      json.dumps(_node(workflow, "2 - GHL")["parameters"]))
        for other in ("6 - GHL", "10 - GHL"):
            params = json.dumps(_node(workflow, other)["parameters"])
            self.assertNotIn("Config", params)
            self.assertIn("PASTE-YOUR-", params)
        content = _node(workflow, "Overview")["parameters"]["content"]
        self.assertNotIn("0b", content)
        self.assertNotIn("Copy the same values", content)

    def test_node_shared_by_two_paths_reads_config_at_the_join(self):
        nodes = [
            {"key": "a", "kind": "trigger.webhook", "label": "1 - Form A", "section": "in"},
            {"key": "b", "kind": "trigger.webhook", "label": "2 - Form B", "section": "in"},
            _ghl("up", "3 - GHL: Upsert Contact"),
        ]
        edges = [{"from": "a", "to": "up"}, {"from": "b", "to": "up"}]
        workflow = _compile(_base(nodes, edges, config={"ghl_location_id": "PASTE-YOUR-X"}))
        conns = workflow["connections"]
        # The join is an ordinary node, so Config goes right in front of it.
        for trigger in ("1 - Form A", "2 - Form B"):
            self.assertEqual(conns[trigger]["main"][0][0]["node"], CONFIG_NODE_NAME)
        self.assertEqual(conns[CONFIG_NODE_NAME]["main"][0][0]["node"],
                         "3 - GHL: Upsert Contact")
        params = json.dumps(_node(workflow, "3 - GHL")["parameters"])
        self.assertIn("$('%s')" % CONFIG_NODE_NAME, params)

    def test_every_archetype_and_job_with_config(self):
        for name, spec in _all_specs():
            with self.subTest(spec=name):
                spec.config = {"ghl_location_id": "PASTE-YOUR-LOCATION-ID",
                               "sheet_id": "PASTE-YOUR-SHEET-ID"}
                workflow = compile_n8n(spec)
                for node_name, ref in _config_refs(workflow):
                    self.assertIn(ref.replace("\\'", "'"), _upstream(workflow, node_name),
                                  node_name)


class TestConfigWithoutTrigger(unittest.TestCase):
    """Defect 2: a trigger-less spec still gets a real Config node, and the
    overview only ever names Config nodes that exist."""

    def _spec(self):
        nodes = [
            {"key": "tidy", "kind": "data.transform", "label": "1 - Tidy", "section": "in"},
            _ghl("up", "2 - GHL: Upsert Contact"),
        ]
        return _base(nodes, [{"from": "tidy", "to": "up"}],
                     config={"ghl_location_id": "PASTE-YOUR-LOCATION-ID"})

    def test_config_inserted_at_entry(self):
        workflow = _compile(self._spec())
        names = [n["name"] for n in workflow["nodes"]]
        self.assertIn(CONFIG_NODE_NAME, names)
        self.assertEqual(workflow["connections"][CONFIG_NODE_NAME]["main"][0][0]["node"],
                         "1 - Tidy")
        for name, ref in _config_refs(workflow):
            self.assertIn(ref, _upstream(workflow, name))
        self.assertIn("1 - Tidy", workflow["pinData"])
        self.assertNotIn(CONFIG_NODE_NAME, workflow["pinData"])

    def test_overview_never_names_a_missing_config_node(self):
        specs = _all_specs() + [("trigger-less", self._spec())]
        for name, spec in specs:
            for config in ({}, {"api_key": "PASTE-YOUR-API-KEY"}):
                with self.subTest(spec=name, config=bool(config)):
                    if name != "trigger-less":
                        spec.config = dict(config)
                    workflow = compile_n8n(spec)
                    names = {n["name"] for n in workflow["nodes"]}
                    content = _node(workflow, "Overview")["parameters"]["content"]
                    for mentioned in re.findall(r"0[a-z]? - Config: Your Settings[^.\n]*",
                                                content):
                        self.assertTrue(any(mentioned.startswith(n) for n in names
                                            if "Config" in n), mentioned)
                    if not any("Config: Your Settings" in n for n in names):
                        self.assertNotIn("Config", content)


class TestConfigReadByNameWithoutConfig(unittest.TestCase):
    """A vault archetype loses `config` on promotion but keeps the params its
    author wrote against the Config node, so compiled alone it still needs
    that node, carrying every key those params read."""

    def test_reads_build_the_config_node(self):
        code = ("const cfg = $('0 - Config: Your Settings').first().json;\n"
                "return [{ json: { team: cfg.bar } }];")
        nodes = [
            {"key": "hook", "kind": "trigger.webhook", "label": "1 - Enquiry Arrives",
             "section": "in"},
            {"key": "call", "kind": "net.http", "label": "2 - Look Up the Account",
             "section": "in", "params": {
                 "url": "={{ $('0 - Config: Your Settings').item.json.foo }}/accounts"}},
            {"key": "code", "kind": "data.code", "label": "3 - Pick the Team",
             "section": "in", "params": {"mode": "runOnceForAllItems", "jsCode": code}},
        ]
        spec = _base(nodes, [{"from": "hook", "to": "call"}, {"from": "call", "to": "code"}])
        self.assertEqual(spec.config, {})
        workflow = _compile(spec)
        configs = [n for n in workflow["nodes"] if "Config: Your Settings" in n["name"]]
        self.assertEqual([n["name"] for n in configs], [CONFIG_NODE_NAME])
        values = {a["name"]: a["value"]
                  for a in configs[0]["parameters"]["assignments"]["assignments"]}
        self.assertEqual(values.get("foo"), "PASTE-YOUR-FOO")
        self.assertEqual(values.get("bar"), "PASTE-YOUR-BAR")
        names = {n["name"] for n in workflow["nodes"]}
        refs = _config_refs(workflow)
        self.assertTrue(refs)
        for name, ref in refs:
            self.assertIn(ref, names)
            self.assertIn(ref, _upstream(workflow, name))
        content = _node(workflow, "Overview")["parameters"]["content"]
        self.assertIn("foo and bar in the {} node".format(CONFIG_NODE_NAME), content)


class TestPromoteStripsClientFields(unittest.TestCase):
    """Defect 3: the vault never keeps client, config or overview."""

    def test_promote_output_and_next_compile(self):
        import tempfile
        from upwork_gen import learn
        spec = _single("ai.agent", {"system_message": "You work for Acme Cleaning."},
                       label="2 - Qualify",
                       extra_nodes=[{"key": "m", "kind": "ai.model", "app": "openai",
                                     "label": "OpenAI", "parent": "x"}],
                       client={"name": "Sam", "company": "Acme Cleaning"},
                       overview={"how_it_works": ["Acme's leads arrive"],
                                 "need_from_you": ["Acme's Slack"]},
                       config={"api_key": "PASTE-YOUR-API-KEY"})
        with tempfile.TemporaryDirectory() as tmp:
            saved = (learn.VAULT_DIR, learn.KEYWORDS_PATH)
            learn.VAULT_DIR = os.path.join(tmp, "archetypes")
            learn.KEYWORDS_PATH = os.path.join(tmp, "keywords.json")
            try:
                report = learn.promote(spec, archetype_id="quality_test_promote")
            finally:
                learn.VAULT_DIR, learn.KEYWORDS_PATH = saved
            self.assertTrue(report["promoted"])
            path = os.path.join(tmp, "archetypes", "quality_test_promote.json")
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            for key in ("client", "config", "overview"):
                self.assertNotIn(key, data)
            # The spec author's own node text is kept.
            self.assertIn("You work for Acme Cleaning.", json.dumps(data["nodes"]))
            again = WorkflowSpec.load(path)
            workflow = compile_n8n(again)
            content = _node(workflow, "Overview")["parameters"]["content"]
            self.assertNotIn("Built for", content)
            self.assertNotIn("Acme's", content)
            self.assertFalse(any("Config: Your Settings" in n["name"]
                                 for n in workflow["nodes"]))
        # The caller's spec is untouched apart from its archetype id.
        self.assertEqual(spec.client["company"], "Acme Cleaning")


class TestNativeAppNodes(unittest.TestCase):
    """Defect 4: a native node never resolves as an HTTP service."""

    def test_monday_native_node(self):
        from upwork_gen.params import resolve_service
        spec = _single("app.action", None, app="monday", label="2 - Monday: Create the Item",
                       config={"sheet_id": "PASTE-YOUR-SHEET-ID"})
        workflow = _compile(spec)
        node = _node(workflow, "2 - Monday")
        self.assertEqual(node["type"], "n8n-nodes-base.mondayCom")
        self.assertIsNone(resolve_service(spec.node("x"), spec))
        config = _node(workflow, CONFIG_NODE_NAME)["parameters"]["assignments"]["assignments"]
        self.assertNotIn("monday_api_token", [a["name"] for a in config])
        content = _node(workflow, "Overview")["parameters"]["content"]
        self.assertNotIn("API token", content)
        self.assertIn("Connect your monday.com credential on its node.", content)
        self.assertNotIn("monday", json.dumps(node["parameters"]).lower().replace(
            "mondaycom", ""))

    def test_calendly_action_is_an_http_service(self):
        # n8n has no Calendly action node (only the trigger), so a Calendly
        # action resolves to the Calendly HTTP service and its config keys.
        from upwork_gen.params import resolve_service, service_config_keys
        spec = _single("app.action", None, app="calendly", label="2 - Calendly: Events")
        self.assertEqual(resolve_service(spec.node("x"), spec)[0], "calendly")
        self.assertIn("calendly_token", service_config_keys(spec))


class TestOverviewEverywhere(unittest.TestCase):
    """Every overview has all three headings, at most 300 tokens, and only
    real prose: no minimum length, no padding tiers, no cut sentences."""

    def _check(self, content, spec):
        words, tokens = overview_words(content)
        self.assertLessEqual(tokens, 300, content)
        for heading in ("### How it works", "### Setup", "### What I need from you"):
            self.assertIn(heading, content)
            after = content.split(heading, 1)[1].lstrip("\n")
            self.assertTrue(after.startswith("- "), heading)
        self.assertNotIn("...", content.replace(spec.title, ""))
        self.assertNotIn("Data in:", content)
        self.assertNotIn("Data out:", content)
        how = content.split("### How it works", 1)[1].split("### Setup", 1)[0]
        # No raw snake_case key lists and no "<Section> runs <labels>" chains,
        # unless the spec author wrote them in their own prose.
        authored = json.dumps([s.note for s in spec.sections] + [spec.overview],
                              ensure_ascii=False)
        for match in re.findall(r"\b[a-z0-9]+_[a-z0-9_]+, [a-z0-9]+_[a-z0-9_]+", how):
            self.assertIn(match, authored, how)
        for section in spec.sections:
            self.assertNotIn("- {} runs ".format(_sentence_case(section.label)), how)
        self.assertIsNone(re.search(r"^- The workflow runs ", how, re.M), how)
        # Section-note bullets are whole sentences of the note.
        if not spec.overview.get("how_it_works"):
            notes = [s.note.strip() for s in spec.sections if s.note]
            for line in how.strip().splitlines():
                body = line[2:].split(": ", 1)[-1]
                owner = [n for n in notes if n.startswith(body)]
                if not owner or ": " not in line:
                    continue
                rest = owner[0][len(body):]
                self.assertTrue(rest == "" or (body[-1] in ".!?" and rest[:1].isspace()),
                                line)

    def test_all_archetypes_and_jobs(self):
        for name, spec in _all_specs():
            with self.subTest(spec=name):
                self._check(_node(compile_n8n(spec), "Overview")["parameters"]["content"],
                            spec)

    def test_with_client_config_and_bullets(self):
        for name, spec in _all_specs():
            with self.subTest(spec=name):
                spec.client = {"company": "Acme Co"}
                spec.config = {"api_key": "PASTE-YOUR-API-KEY"}
                spec.overview = {"need_from_you": ["Slack access"]}
                content = _node(compile_n8n(spec), "Overview")["parameters"]["content"]
                self._check(content, spec)
                self.assertIn("Built for Acme Co", content)
                self.assertIn("api_key", content)

    def test_thin_spec_stays_short_and_clean(self):
        spec = _single("app.action", None, app="slack", label="2 - Tell Sales")
        content = overview_markdown(spec)
        self.assertLess(overview_words(content)[0], 100)
        self._check(content, spec)

    def test_long_notes_cut_at_a_sentence(self):
        long_note = " ".join("Sentence number {} explains one more detail of this "
                             "step.".format(i) for i in range(40))
        spec = _single("app.action", None, app="slack", label="2 - Tell Sales")
        for section in spec.sections:
            section.note = long_note
        spec.overview = {"setup": ["One. Two."]}
        content = overview_markdown(spec)
        self.assertLessEqual(overview_words(content)[1], 300)
        for line in content.split("### How it works", 1)[1].split("### Setup")[0].split("\n"):
            if line.startswith("- "):
                self.assertTrue(line.endswith("step."), line)

    def test_setup_lists_native_credentials(self):
        spec = _single("app.action", None, app="slack", label="2 - Tell Sales",
                       overview={"setup": ["Invite the bot to #sales"]})
        content = overview_markdown(spec)
        self.assertIn("### Setup", content)
        self.assertIn("- Invite the bot to #sales", content)


class TestSetNodesDistinct(unittest.TestCase):
    """Defect 6: no two Set nodes in one workflow list the same fields."""

    def test_generic_verbs_never_match_part_of_a_field(self):
        from upwork_gen.params import _key_matches
        for verb, key in (("check", "check_in_date"), ("send", "send_at"),
                          ("update", "last_update"), ("build", "build_id"),
                          ("run", "run_id"), ("work", "work_order"), ("add", "add_on"),
                          ("get", "get_date"), ("set", "set_id"), ("make", "make_model"),
                          ("create", "create_date")):
            self.assertFalse(_key_matches(verb, key), (verb, key))
        self.assertTrue(_key_matches("email", "email"))
        self.assertTrue(_key_matches("class", "lead_class"))
        self.assertTrue(_key_matches("run", "run"))

    def test_every_archetype_and_job(self):
        for name, spec in _all_specs():
            for config in ({}, {"api_key": "PASTE-YOUR-API-KEY"}):
                with self.subTest(spec=name, config=bool(config)):
                    spec.config = dict(config)
                    workflow = compile_n8n(spec)
                    seen = {}
                    for node in workflow["nodes"]:
                        if node["type"] != "n8n-nodes-base.set" or \
                                "Config: Your Settings" in node["name"]:
                            continue
                        fields = tuple(a["name"] for a in node["parameters"].get(
                            "assignments", {}).get("assignments", []))
                        self.assertNotIn(fields, seen, "{} repeats {}".format(
                            node["name"], seen.get(fields)))
                        seen[fields] = node["name"]


class TestTableNames(unittest.TestCase):
    """Defect 7: tabs are named for what they hold, and later steps reuse them."""

    def _names(self, workflow, prefix):
        params = _node(workflow, prefix)["parameters"]
        if "sheetName" in params:
            return params["documentId"]["value"], params["sheetName"]["value"]
        return params["base"]["value"], params["table"]["value"]

    def test_update_reuses_upstream_sheet_and_document(self):
        nodes = [
            {"key": "hook", "kind": "trigger.webhook", "label": "1 - In", "section": "in"},
            {"key": "log", "kind": "app.action", "app": "googleSheets", "op": "append",
             "label": "2 - Log It to the Requests Sheet", "section": "in",
             "params": {"document": "1AbCdEf"}},
            {"key": "mark", "kind": "app.action", "app": "googleSheets", "op": "update",
             "label": "3 - Mark the Row Handled", "section": "out"},
            {"key": "fresh", "kind": "app.action", "app": "googleSheets", "op": "append",
             "label": "4 - Write the Weekly Totals", "section": "out"},
        ]
        edges = [{"from": "hook", "to": "log"}, {"from": "log", "to": "mark"},
                 {"from": "mark", "to": "fresh"}]
        workflow = _compile(_base(nodes, edges))
        self.assertEqual(self._names(workflow, "2 - Log"), ("1AbCdEf", "Requests"))
        self.assertEqual(self._names(workflow, "3 - Mark"), ("1AbCdEf", "Requests"))
        doc, sheet = self._names(workflow, "4 - Write")
        self.assertEqual(sheet, "Weekly Totals")
        self.assertEqual(doc, "PASTE-YOUR-GOOGLE-SHEET-ID")

    def test_leading_verbs_dropped_nouns_kept(self):
        from upwork_gen.params import _sheet_name
        from upwork_gen.spec import Node
        cases = {"8 - Mark the Row Handled": "Sheet1", "16 - Execution Log Row": "Execution Log",
                 "4 - Log It to the Requests Sheet": "Requests",
                 "3b - Park It in Needs Review With the Failing Field": "Needs Review",
                 "8 - Airtable: Create the Ops Project Record": "Ops Project"}
        for label, expected in cases.items():
            node = Node(key="n", kind="app.action", label=label, app="googleSheets")
            self.assertEqual(_sheet_name(node), expected, label)

    def test_ai_request_handler_job(self):
        workflow = compile_n8n(_job_spec("ai-automation-developer-openai-n8n"))
        log = self._names(workflow, "4 - Log It")
        done = self._names(workflow, "8 - Mark the Row Handled")
        self.assertEqual(log[1], "Requests")
        self.assertEqual(done, log)
        self.assertNotEqual(done[1], "Mark Handled")

    def test_crm_job(self):
        workflow = compile_n8n(_job_spec("crm-automation-multi-system-api-claude-n8n"))
        self.assertEqual(self._names(workflow, "3b - Park")[1], "Needs Review")
        self.assertEqual(self._names(workflow, "8 - Airtable")[1], "Ops Project")
        for node in workflow["nodes"]:
            if node["type"] in ("n8n-nodes-base.airtable", "n8n-nodes-base.googleSheets"):
                table = node["parameters"].get("table") or node["parameters"].get("sheetName")
                first = table["value"].split()[0].lower()
                self.assertNotIn(first, ("park", "create", "mark", "log", "update"),
                                 node["name"])


class TestParserJsonSchema(unittest.TestCase):
    """Defect 8: a JSON Schema goes in as a manual schema and names the fields."""

    SCHEMA = {"type": "object", "properties": {"tier": {"type": "string",
                                                        "enum": ["A", "B"]},
                                               "reason": {"type": "string"},
                                               "score": {"type": "number"}},
              "required": ["tier"]}

    def _spec(self, params):
        return _single("ai.llm", None, label="2 - Score",
                       extra_nodes=[{"key": "m", "kind": "ai.model", "app": "anthropic",
                                     "label": "Claude", "parent": "x"},
                                    {"key": "p", "kind": "ai.parser", "label": "Tier",
                                     "parent": "x", "params": params}])

    def test_schema_shorthand_json_schema(self):
        workflow = _compile(self._spec({"schema": self.SCHEMA}))
        params = _node(workflow, "Tier")["parameters"]
        self.assertEqual(params["schemaType"], "manual")
        self.assertEqual(json.loads(params["inputSchema"]), self.SCHEMA)
        self.assertNotIn("jsonSchemaExample", params)
        self.assertNotIn("schema", params)
        system = _node(workflow, "2 - Score")["parameters"]["messages"]["messageValues"][0][
            "message"]
        self.assertIn("Return JSON with exactly these fields: tier, reason, score.", system)

    def test_raw_input_schema_names_the_fields(self):
        workflow = _compile(self._spec({"inputSchema": json.dumps(self.SCHEMA)}))
        system = _node(workflow, "2 - Score")["parameters"]["messages"]["messageValues"][0][
            "message"]
        self.assertIn("tier, reason, score", system)

    def test_example_schema_still_from_json(self):
        workflow = _compile(self._spec({"schema": {"tier": "A", "type": "lead"}}))
        params = _node(workflow, "Tier")["parameters"]
        self.assertEqual(params["schemaType"], "fromJson")
        self.assertEqual(json.loads(params["jsonSchemaExample"]), {"tier": "A", "type": "lead"})


class TestEntryNodeSkipsErrorTrigger(unittest.TestCase):
    """Reviewer note 9."""

    def test_sample_pins_on_the_main_trigger(self):
        nodes = [
            {"key": "err", "kind": "trigger.app", "app": "n8n", "op": "error_trigger",
             "label": "9 - Any Step Fails", "section": "out"},
            {"key": "hook", "kind": "trigger.webhook", "label": "1 - Enquiry Arrives",
             "section": "in"},
            {"key": "alert", "kind": "app.action", "app": "slack", "label": "10 - Alert",
             "section": "out"},
            {"key": "tidy", "kind": "data.transform", "label": "2 - Tidy", "section": "in"},
        ]
        spec = _base(nodes, [{"from": "err", "to": "alert"}, {"from": "hook", "to": "tidy"}])
        self.assertEqual(spec.entry_node().key, "hook")
        workflow = _compile(spec)
        self.assertIn("1 - Enquiry Arrives", workflow["pinData"])
        self.assertNotIn("9 - Any Step Fails", workflow["pinData"])

    def test_trigger_less_skips_error_trigger(self):
        nodes = [
            {"key": "err", "kind": "trigger.app", "app": "n8n", "op": "error_trigger",
             "label": "9 - Any Step Fails", "section": "out"},
            {"key": "a", "kind": "data.transform", "label": "1 - Tidy", "section": "in"},
        ]
        spec = _base(nodes, [])
        self.assertEqual(spec.entry_node().key, "a")


class TestServiceAliases(unittest.TestCase):
    """Reviewer note 10."""

    def test_high_level_summary_is_not_ghl(self):
        spec = _single("net.http", None, label="6 - Send a High Level Summary")
        params = _node(_compile(spec), "6 - Send")["parameters"]
        self.assertNotIn("leadconnectorhq", params["url"])
        self.assertIn("example.com", params["url"])
        aliases = load_services()["gohighlevel"]["aliases"]
        self.assertNotIn("high level", aliases)
        for alias in ("highlevel", "gohighlevel", "ghl", "leadconnector"):
            self.assertIn(alias, aliases)

    def test_ghl_conversations_use_their_version(self):
        spec = _single("net.http", None, label="2 - GHL: Send the SMS Reply")
        params = _node(_compile(spec), "2 - GHL")["parameters"]
        self.assertIn("/conversations/messages", params["url"])
        versions = [h["value"] for h in params["headerParameters"]["parameters"]
                    if h["name"] == "Version"]
        self.assertEqual(versions, ["2021-04-15"])
        for key, op in load_services()["gohighlevel"]["operations"].items():
            if op["path"].startswith("/conversations"):
                self.assertEqual(op.get("headers", {}).get("Version"), "2021-04-15", key)


class TestConfigKeys(unittest.TestCase):
    """Reviewer note 11."""

    def test_bad_key_warns_with_the_fix(self):
        spec = _single("flow.noop", None, config={"Sheet ID": "PASTE-YOUR-SHEET-ID",
                                                  "good_key": "x"})
        warnings = spec.validate()
        bad = [w for w in warnings if "Sheet ID" in w]
        self.assertEqual(len(bad), 1)
        self.assertIn("'sheet_id'", bad[0])
        self.assertFalse(any("good_key" in w for w in warnings))

    def test_bad_key_still_yields_a_valid_expression(self):
        spec = _single("app.action", None, app="googleSheets", label="2 - Log the Lead",
                       config={"Sheet ID": "PASTE-YOUR-SHEET-ID"})
        params = _node(_compile(spec), "2 - Log the Lead")["parameters"]
        value = params["documentId"]["value"]
        self.assertEqual(value, '={{ $(\'%s\').item.json["Sheet ID"] }}' % CONFIG_NODE_NAME)
        self.assertNotIn(".json.Sheet ID", value)


class TestFieldLookupsSkipConfig(unittest.TestCase):
    """Reviewer note 12: business data never reads from the Config node."""

    def test_ai_read_back_skips_config(self):
        spec = _single("ai.llm", None, label="2 - Summarize",
                       extra_nodes=[
                           {"key": "m", "kind": "ai.model", "app": "anthropic",
                            "label": "Claude", "parent": "x"},
                           {"key": "p", "kind": "ai.parser", "label": "Summary",
                            "parent": "x", "params": {"schema": {"summary": "text"}}},
                           {"key": "s", "kind": "app.action", "app": "slack",
                            "label": "3 - Tell Sales", "section": "out"}],
                       config={"slack_channel": "#sales"})
        spec.edges.append(Edge(src="x", dst="s"))
        workflow = _compile(spec)
        text = _node(workflow, "3 - Tell Sales")["parameters"]["text"]
        self.assertIn("$('1 - Enquiry Arrives').item.json.", text)
        self.assertNotIn("Config", text)

    def test_first_set_after_config_lists_the_payload(self):
        spec = _single("data.transform", None, label="2 - Tidy",
                       config={"api_key": "PASTE-YOUR-API-KEY"})
        params = _node(_compile(spec), "2 - Tidy")["parameters"]
        names = [a["name"] for a in params["assignments"]["assignments"]]
        self.assertIn("email", names)
        for assignment in params["assignments"]["assignments"]:
            self.assertNotIn("Config", assignment["value"])


class TestPastePlaceholders(unittest.TestCase):
    """Every placeholder the compiler writes reads PASTE-YOUR-..."""

    def test_no_bare_your_placeholders(self):
        pattern = re.compile(r"(?<!PASTE-)YOUR_")
        for name, spec in _all_specs():
            for config in ({}, {"ghl_location_id": "PASTE-YOUR-LOCATION-ID"}):
                with self.subTest(spec=name, config=bool(config)):
                    own = json.dumps(spec.to_dict())
                    if pattern.search(own):
                        continue  # the spec author's own text, not the compiler's
                    spec.config = dict(config)
                    text = json.dumps(compile_n8n(spec))
                    self.assertIsNone(pattern.search(text), name)

    def test_placeholder_shapes(self):
        spec = _single("net.http", None, label="2 - GHL: Upsert Contact")
        params = json.dumps(_node(_compile(spec), "2 - GHL")["parameters"])
        self.assertIn("PASTE-YOUR-GHL-API-KEY", params)
        self.assertIn("PASTE-YOUR-GHL-LOCATION-ID", params)
        sheet = _single("app.action", None, app="googleSheets", label="2 - Log the Lead")
        doc = _node(_compile(sheet), "2 - Log")["parameters"]["documentId"]["value"]
        self.assertEqual(doc, "PASTE-YOUR-GOOGLE-SHEET-ID")
        table = _single("app.action", None, app="airtable", label="2 - Create Job Record")
        base = _node(_compile(table), "2 - Create")["parameters"]["base"]["value"]
        self.assertEqual(base, "PASTE-YOUR-AIRTABLE-BASE-ID")
        content = overview_markdown(spec)
        self.assertIn("PASTE-YOUR-", content)
        self.assertNotIn("YOUR_", content)
        for service in load_services().values():
            for value in service.get("placeholders", {}).values():
                self.assertNotIn("YOUR_", value)



if __name__ == "__main__":
    unittest.main()


# --------------------------------------------------------------------------
# Fix round 2: one Config node, never in front of a trigger, clean titles,
# each app once.
# --------------------------------------------------------------------------


def _targets(workflow):
    return {t["node"] for ports in workflow["connections"].values()
            for groups in ports.values() for group in groups for t in group}


def _trigger_names(workflow):
    return {n["name"] for n in workflow["nodes"]
            if n["type"].lower().endswith("trigger") or n["type"].endswith(".webhook")
            or "Trigger" in n["type"]}


_ANY_REF = re.compile(r"\$\(\s*'((?:[^'\\]|\\.)*)'\s*\)")


def _strings(value):
    """Every string in a JSON value."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for inner in value.values():
            yield from _strings(inner)
    elif isinstance(value, list):
        for inner in value:
            yield from _strings(inner)


def _if_bodies(code):
    """(start, end) of the `{ ... }` body of every `if (...) { ... }` in a
    code string. A plain bracket count that ignores braces and parens inside
    strings and comments: good enough for the one narrow exemption below,
    where a stray brace can only shrink or drop a body, never invent one."""
    def close(start, opener, closer):
        depth = 0
        for i in range(start, len(code)):
            depth += (code[i] == opener) - (code[i] == closer)
            if depth == 0:
                return i
        return -1

    bodies = []
    for match in re.finditer(r"\bif\s*\(", code):
        cond_end = close(match.end() - 1, "(", ")")
        if cond_end < 0:
            continue
        brace = re.compile(r"\s*\{").match(code, cond_end + 1)
        if brace:
            body_end = close(brace.end() - 1, "{", "}")
            if body_end > 0:
                bodies.append((brace.end() - 1, body_end))
    return bodies


def _dominance_problems(workflow):
    """(reader, referenced node) for every `$('X')`, Config or not, whose X is
    missing, is the reader itself, or does not run on every path from every
    trigger into the reader (n8n: "Referenced node is unexecuted"). An AI
    sub-node reads as its parent. Pass the workflow as the file carries it
    (ascii_safe_obj), where names and references are folded alike."""
    succ, parent = {}, {}
    for src, ports in workflow["connections"].items():
        for port, groups in ports.items():
            for group in groups:
                for target in group:
                    if port == "main":
                        succ.setdefault(src, set()).add(target["node"])
                    else:
                        parent[src] = target["node"]
    names = {n["name"] for n in workflow["nodes"]}
    flow = {n["name"] for n in workflow["nodes"]
            if not n["type"].endswith("stickyNote") and n["name"] not in parent}
    fed = {name for targets in succ.values() for name in targets}
    roots = [name for name in flow if name not in fed]

    def runs_first(gate, target):
        seen, stack = set(), [r for r in roots if r != gate]
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            if current == target:
                return False
            stack.extend(d for d in succ.get(current, ()) if d != gate)
        return True

    def guarded(node, ref, text, at):
        # A Code node evaluates `$('X')` lazily, so reading a branch that fed
        # it, inside an `if` body that mirrors the branch rule, is valid n8n
        # (the Shopify/WooCommerce store switch). The guard itself is unseen.
        return (node["type"] == "n8n-nodes-base.code"
                and node["name"] in succ.get(ref, ())
                and any(start < at < end for start, end in _if_bodies(text)))

    problems = []
    for node in workflow["nodes"]:
        if node["type"].endswith("stickyNote"):
            continue
        reader, hops = node["name"], 0
        while reader in parent and hops < 8:
            reader, hops = parent[reader], hops + 1
        for text in _strings(node.get("parameters", {})):
            for match in _ANY_REF.finditer(text):
                ref = re.sub(r"\\(.)", r"\1", match.group(1))
                if ref not in names or ref == reader or (
                        not runs_first(ref, reader)
                        and not guarded(node, ref, text, match.start())):
                    problems.append((node["name"], ref))
    return problems


class TestSingleConfigNode(unittest.TestCase):
    """Exactly one Config node per workflow, where it runs before the most
    readers; never in front of any trigger."""

    def test_after_the_merge_of_several_triggers(self):
        nodes = [
            {"key": "a", "kind": "trigger.webhook", "label": "1 - Website Form", "section": "in"},
            {"key": "b", "kind": "trigger.webhook", "label": "2 - Typeform", "section": "in"},
            {"key": "c", "kind": "trigger.schedule", "label": "3 - Nightly Import",
             "section": "in"},
            {"key": "m", "kind": "data.merge", "label": "4 - Merge the Sources", "section": "in"},
            _ghl("up", "5 - GHL: Upsert Contact", "out"),
        ]
        edges = [{"from": "a", "to": "m"}, {"from": "b", "to": "m"}, {"from": "c", "to": "m"},
                 {"from": "m", "to": "up"}]
        workflow = _compile(_base(nodes, edges,
                                  config={"ghl_location_id": "PASTE-YOUR-LOCATION-ID"}))
        names = [n["name"] for n in workflow["nodes"]]
        self.assertEqual([n for n in names if "Config" in n], [CONFIG_NODE_NAME])
        conns = workflow["connections"]
        self.assertEqual(conns["4 - Merge the Sources"]["main"][0][0]["node"],
                         CONFIG_NODE_NAME)
        self.assertEqual(conns[CONFIG_NODE_NAME]["main"][0][0]["node"],
                         "5 - GHL: Upsert Contact")
        for trigger in ("1 - Website Form", "2 - Typeform", "3 - Nightly Import"):
            self.assertEqual(conns[trigger]["main"][0][0]["node"], "4 - Merge the Sources")
        params = json.dumps(_node(workflow, "5 - GHL")["parameters"])
        self.assertIn("$('%s')" % CONFIG_NODE_NAME, params)
        content = _node(workflow, "Overview")["parameters"]["content"]
        self.assertIn("in the {} node".format(CONFIG_NODE_NAME), content)
        self.assertNotIn("Copy the same values", content)

    def test_error_trigger_only_config_goes_after_it(self):
        nodes = [
            {"key": "err", "kind": "trigger.app", "app": "n8n", "op": "error_trigger",
             "label": "1 - Any Workflow Fails", "section": "in"},
            _ghl("tag", "2 - GHL: Tag the Contact as Errored"),
            {"key": "alert", "kind": "app.action", "app": "slack", "label": "3 - Alert the Team",
             "section": "out"},
        ]
        edges = [{"from": "err", "to": "tag"}, {"from": "tag", "to": "alert"}]
        workflow = _compile(_base(nodes, edges, config={"ghl_api_key": "PASTE-YOUR-KEY"}))
        conns = workflow["connections"]
        self.assertNotIn("1 - Any Workflow Fails", _targets(workflow))
        self.assertEqual(conns["1 - Any Workflow Fails"]["main"][0][0]["node"],
                         CONFIG_NODE_NAME)
        self.assertEqual(conns[CONFIG_NODE_NAME]["main"][0][0]["node"],
                         "2 - GHL: Tag the Contact as Errored")
        self.assertIn("$('%s')" % CONFIG_NODE_NAME,
                      json.dumps(_node(workflow, "2 - GHL")["parameters"]))

    def test_unread_config_still_named_plainly(self):
        spec = _single("app.action", None, app="slack", label="2 - Tell Sales",
                       config={"booking_link": "PASTE-YOUR-BOOKING-LINK"})
        workflow = _compile(spec)
        self.assertEqual([n["name"] for n in workflow["nodes"] if "Config" in n["name"]],
                         [CONFIG_NODE_NAME])
        content = _node(workflow, "Overview")["parameters"]["content"]
        self.assertIn("- Fill in booking_link in the {} node.".format(CONFIG_NODE_NAME),
                      content)

    def test_reported_repros(self):
        repros = [("claude_n8n_lead_management", load_archetype("claude_n8n_lead_management"))]
        path = os.path.join(JOBS_DIR, "otter-ringcentral-docketwise-m365-integration",
                            "spec.json")
        if os.path.exists(path):
            repros.append(("otter", WorkflowSpec.load(path)))
        for name, spec in repros:
            with self.subTest(spec=name):
                spec.config = {"ghl_location_id": "PASTE-YOUR-LOCATION-ID"}
                workflow = compile_n8n(spec)
                configs = [n["name"] for n in workflow["nodes"] if "Config" in n["name"]]
                self.assertEqual(configs, [CONFIG_NODE_NAME])
                content = _node(workflow, "Overview")["parameters"]["content"]
                self.assertEqual(len(re.findall(r"Config: Your Settings", content)),
                                 len(re.findall(r"in the 0 - Config: Your Settings node",
                                                content)))
                self.assertNotIn("0b", content)

    def test_whole_corpus_one_config_never_before_a_trigger(self):
        for name, spec in _all_specs():
            for config in ({"ghl_location_id": "PASTE-YOUR-LOCATION-ID"}, {}):
                with self.subTest(spec=name, config=bool(config)):
                    spec.config = dict(config)
                    workflow = compile_n8n(spec)
                    configs = [n["name"] for n in workflow["nodes"]
                               if "Config: Your Settings" in n["name"]]
                    # A spec whose own params read the Config node by name (a
                    # promoted archetype) gets one even with `config` empty.
                    wanted = config or config_keys_read(spec) is not None
                    self.assertEqual(configs, [CONFIG_NODE_NAME] if wanted else [])
                    if not config:
                        continue
                    downstream = {t["node"] for group in
                                  workflow["connections"].get(CONFIG_NODE_NAME, {}).get(
                                      "main", []) for t in group}
                    self.assertFalse(downstream & _trigger_names(workflow), downstream)
                    # Every reference, Config or not, names a node that runs on
                    # every path into its reader, not merely one upstream.
                    self.assertEqual(_dominance_problems(ascii_safe_obj(workflow)), [])


class TestAsciiTitles(unittest.TestCase):
    def test_arrows_and_symbols_never_vanish(self):
        from upwork_gen.generate import ascii_safe
        self.assertEqual(ascii_safe("CRM \u2194 Airtable Sync"), "CRM - Airtable Sync")
        self.assertEqual(ascii_safe("CRM\u2194Airtable"), "CRM - Airtable")
        self.assertEqual(ascii_safe("Back \u2190 Next"), "Back - Next")
        self.assertEqual(ascii_safe("Wait\u2026"), "Wait...")
        self.assertEqual(ascii_safe("3 \u00d7 5"), "3 x 5")
        self.assertEqual(ascii_safe("\u2713 Done"), "OK Done")
        self.assertEqual(ascii_safe("Hello \u2605 world"), "Hello world")
        self.assertEqual(ascii_safe("Lead \u2192 CRM"), "Lead -> CRM")
        self.assertEqual(ascii_safe("caf\u00e9"), "cafe")
        self.assertEqual(ascii_safe('{\n  "a": "b"\n}'), '{\n  "a": "b"\n}')

    def test_compiled_title_keeps_its_separator(self):
        from upwork_gen.generate import ascii_safe
        spec = _single("app.action", None, app="slack", label="2 - Tell Sales")
        spec.title = "CRM \u2194 Airtable Sync"
        text = ascii_safe(json.dumps(compile_n8n(spec), indent=2, ensure_ascii=False))
        workflow = json.loads(text)
        self.assertEqual(workflow["name"], "CRM - Airtable Sync")
        self.assertIn("## CRM - Airtable Sync", _node(workflow, "Overview")["parameters"][
            "content"])
        self.assertNotIn("CRM  Airtable", text)


class TestSetupListsEachAppOnce(unittest.TestCase):
    def _sections(self, content):
        setup = content.split("### Setup", 1)[1].split("### What I need from you", 1)[0]
        need = content.split("### What I need from you", 1)[1]
        return setup, need

    def test_each_app_once_per_section(self):
        nodes = [
            {"key": "hook", "kind": "trigger.webhook", "label": "1 - Enquiry Arrives",
             "section": "in"},
            {"key": "a", "kind": "app.action", "app": "slack", "label": "2 - Tell Sales",
             "section": "out"},
            {"key": "b", "kind": "app.action", "app": "googleSheets", "label": "3 - Log It",
             "section": "out"},
            {"key": "c", "kind": "app.action", "app": "slack", "label": "4 - Tell Ops",
             "section": "out"},
        ]
        edges = [{"from": "hook", "to": "a"}, {"from": "a", "to": "b"}, {"from": "b", "to": "c"}]
        setup, need = self._sections(overview_markdown(_base(nodes, edges)))
        for app in ("Slack", "Google Sheets"):
            self.assertEqual(setup.count(app), 1, setup)
            self.assertEqual(need.count(app), 1, need)
        self.assertEqual(need.count("Access to your"), 1, need)

    def test_http_url_names_its_service(self):
        spec = _single("net.http", {"method": "POST",
                                    "url": "https://api.hubapi.com/crm/v3/objects/contacts"},
                       label="2 - Create the Contact")
        setup, need = self._sections(overview_markdown(spec))
        self.assertIn("HubSpot", setup)
        self.assertIn("HubSpot", need)


# --------------------------------------------------------------------------
# Fix round 3: read-backs only from nodes that ran, ASCII folded on the
# object, app triggers never borrow Calendly's node.
# --------------------------------------------------------------------------

import glob  # noqa: E402
import tempfile  # noqa: E402

from upwork_gen.generate import generate_from_spec, write_output  # noqa: E402

# The reviewer's config block, injected into every corpus spec.
_CFG = {"ghl_api_key": "PASTE-YOUR-GHL-API-KEY", "ghl_location_id": "PASTE-YOUR-LOCATION-ID",
        "slack_channel": "#new-leads", "booking_link": "https://cal.com/your-team/intro",
        "sheet_id": "PASTE-YOUR-SHEET-ID"}


def _corpus():
    """(name, raw spec) for every vault archetype and example, and every n8n
    job spec on this machine (read only, never written)."""
    out = []
    paths = [os.path.join(ROOT, "vault", "archetypes", a + ".json") for a in ARCHETYPE_IDS]
    paths += sorted(glob.glob(os.path.join(ROOT, "examples", "*.json")))
    for path in paths + sorted(glob.glob(os.path.join(JOBS_DIR, "*", "spec.json"))):
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        if path.endswith("spec.json") and raw.get("platform") != "n8n":
            continue
        out.append((os.path.relpath(path, os.path.dirname(ROOT)), raw))
    return out


def _file_view(raw, config=False):
    """A corpus spec compiled and folded exactly as write_output writes it."""
    raw = copy.deepcopy(raw)
    if config:
        raw["config"] = dict(_CFG)
        raw.setdefault("client", {"company": "Acme Roofing"})
    spec = WorkflowSpec.from_dict(raw)
    spec.validate()
    return ascii_safe_obj(compile_n8n(spec))


def _slack_text(workflow, prefix):
    return _node(workflow, prefix)["parameters"]["text"]


_MODEL = {"key": "m", "kind": "ai.model", "app": "anthropic", "label": "Claude", "parent": "ai"}
_PARSER = {"key": "p", "kind": "ai.parser", "label": "Summary", "parent": "ai",
           "params": {"schema": {"summary": "text"}}}
_AI = {"key": "ai", "kind": "ai.llm", "label": "4 - Summarize the Lead", "section": "ai"}
_SLACK = {"key": "slack", "kind": "app.action", "app": "slack", "label": "5 - Tell Sales",
          "section": "out"}


class TestReadBacksOnlyFromNodesThatRan(unittest.TestCase):
    """Blocking defect: after an AI step, a field read back from an earlier
    node names a node that runs on every path into the reader, or reads the
    incoming item. Never a Set on one branch or one of several triggers."""

    def test_set_on_one_branch_is_skipped_for_the_only_trigger(self):
        nodes = [
            {"key": "hook", "kind": "trigger.webhook", "label": "1 - New Lead Webhook",
             "section": "in"},
            {"key": "gate", "kind": "flow.branch", "label": "2 - Company Fields Messy?",
             "section": "in"},
            {"key": "tidy", "kind": "data.transform", "label": "3 - Tidy the Company Fields",
             "section": "in"},
            dict(_AI), dict(_MODEL), copy.deepcopy(_PARSER), dict(_SLACK),
        ]
        edges = [{"from": "hook", "to": "gate"},
                 {"from": "gate", "to": "tidy", "branch": "true"},
                 {"from": "gate", "to": "ai", "branch": "false"},
                 {"from": "tidy", "to": "ai"}, {"from": "ai", "to": "slack"}]
        workflow = ascii_safe_obj(_compile(_base(nodes, edges)))
        text = _slack_text(workflow, "5 - Tell Sales")
        self.assertNotIn("3 - Tidy the Company Fields", text)
        self.assertIn("$('1 - New Lead Webhook').item.json.name", text)
        self.assertEqual(_dominance_problems(workflow), [])

    def test_two_triggers_read_back_from_their_merge(self):
        nodes = [
            {"key": "web", "kind": "trigger.webhook", "label": "1 - Website Lead",
             "section": "in"},
            {"key": "form", "kind": "trigger.form", "label": "2 - Typeform Lead",
             "section": "in"},
            {"key": "merge", "kind": "data.merge", "label": "3 - One Lead Shape",
             "section": "in"},
            dict(_AI), dict(_MODEL), copy.deepcopy(_PARSER), dict(_SLACK),
        ]
        edges = [{"from": "web", "to": "merge"}, {"from": "form", "to": "merge"},
                 {"from": "merge", "to": "ai"}, {"from": "ai", "to": "slack"}]
        for config in ({}, {"ghl_location_id": "PASTE-YOUR-LOCATION-ID"}):
            with self.subTest(config=bool(config)):
                workflow = ascii_safe_obj(_compile(_base(nodes, edges, config=config)))
                text = _slack_text(workflow, "5 - Tell Sales")
                self.assertNotIn("1 - Website Lead", text)
                self.assertIn("$('3 - One Lead Shape').item.json.", text)
                self.assertEqual(_dominance_problems(workflow), [])

    def test_triggers_meeting_at_an_if_read_back_from_the_if(self):
        nodes = [
            {"key": "web", "kind": "trigger.webhook", "label": "1 - Website Lead",
             "section": "in"},
            {"key": "chat", "kind": "trigger.webhook", "label": "2 - Chat Lead",
             "section": "in"},
            {"key": "gate", "kind": "flow.branch", "label": "3 - Not a Duplicate?",
             "section": "in"},
            dict(_AI), dict(_MODEL), copy.deepcopy(_PARSER), dict(_SLACK),
        ]
        edges = [{"from": "web", "to": "gate"}, {"from": "chat", "to": "gate"},
                 {"from": "gate", "to": "ai", "branch": "true"}, {"from": "ai", "to": "slack"}]
        workflow = ascii_safe_obj(_compile(_base(nodes, edges)))
        text = _slack_text(workflow, "5 - Tell Sales")
        self.assertIn("$('3 - Not a Duplicate?').item.json.", text)
        self.assertEqual(_dominance_problems(workflow), [])

    def test_nothing_qualifies_reads_the_incoming_item(self):
        nodes = [
            {"key": "web", "kind": "trigger.webhook", "label": "1 - Website Lead",
             "section": "in"},
            {"key": "chat", "kind": "trigger.webhook", "label": "2 - Chat Lead",
             "section": "in"},
            {"key": "enrich", "kind": "net.http", "label": "3 - Enrich the Company",
             "section": "in"},
            dict(_AI), dict(_MODEL), copy.deepcopy(_PARSER), dict(_SLACK),
        ]
        edges = [{"from": "web", "to": "enrich"}, {"from": "chat", "to": "enrich"},
                 {"from": "enrich", "to": "ai"}, {"from": "ai", "to": "slack"}]
        workflow = ascii_safe_obj(_compile(_base(nodes, edges)))
        text = _slack_text(workflow, "5 - Tell Sales")
        self.assertNotIn("$(", text)
        self.assertIn("{{ $json.name }}", text)
        self.assertEqual(_dominance_problems(workflow), [])

    def test_code_node_reads_a_branch_only_inside_an_if_body(self):
        """A Code node fed by both sides of a Switch may read either side
        inside an `if` body; the same read outside one is still reported."""
        def workflow(code):
            nodes = [{"name": n, "type": t, "parameters": {}} for n, t in (
                ("1 - Hook", "n8n-nodes-base.webhook"), ("2 - Store?", "n8n-nodes-base.switch"),
                ("3a - Shopify", "n8n-nodes-base.httpRequest"),
                ("3b - Woo", "n8n-nodes-base.httpRequest"))]
            nodes.append({"name": "4 - One Shape", "type": "n8n-nodes-base.code",
                          "parameters": {"jsCode": code}})
            link = lambda *targets: {"main": [[{"node": t, "type": "main", "index": 0}
                                               for t in targets]]}
            return {"nodes": nodes, "connections": {
                "1 - Hook": link("2 - Store?"), "2 - Store?": link("3a - Shopify", "3b - Woo"),
                "3a - Shopify": link("4 - One Shape"), "3b - Woo": link("4 - One Shape")}}

        guarded = ("let out = {};\nif (platform === 'shopify') { out = $('3a - Shopify').first().json; }\n"
                   "if (platform === 'woo') {\n  out = $('3b - Woo').all()[0].json;\n}\nreturn [out];")
        self.assertEqual(_dominance_problems(workflow(guarded)), [])
        bare = "const a = $('3a - Shopify').first().json;\nif (a) { return [a]; }"
        self.assertEqual(_dominance_problems(workflow(bare)), [("4 - One Shape", "3a - Shopify")])
        in_condition = "if ($('3a - Shopify').first()) { return []; }"
        self.assertEqual(_dominance_problems(workflow(in_condition)),
                         [("4 - One Shape", "3a - Shopify")])

    def test_reported_archetypes(self):
        cases = [("claude_n8n_lead_management", "Facebook Lead Ad Submitted",
                  ("Upsert Contact & Company", "Add to Nurture")),
                 ("healthcare_sf_hubspot_ai_agent_sync", "Salesforce Record Created or Updated",
                  ("Alert: Normalization Conflict",))]
        for archetype_id, trigger, readers in cases:
            with open(os.path.join(ROOT, "vault", "archetypes", archetype_id + ".json"),
                      "r", encoding="utf-8") as fh:
                raw = json.load(fh)
            for config in (False, True):
                with self.subTest(archetype=archetype_id, config=config):
                    workflow = _file_view(raw, config)
                    for reader in readers:
                        params = json.dumps(_node(workflow, reader)["parameters"])
                        self.assertNotIn("$('{}')".format(trigger), params)
                        self.assertIn(".item.json.", params)
                    self.assertEqual(_dominance_problems(workflow), [])

    def test_valid_read_backs_are_unchanged(self):
        """A Set or trigger that already runs on every path stays the source,
        ahead of a nearer Merge that only combines API results."""
        workflow = ascii_safe_obj(compile_n8n(load_archetype("reporting_digest")))
        self.assertIn("$('Build Date Window').item.json.run_at",
                      _slack_text(workflow, "Post to #leadership"))

    def test_whole_corpus_every_reference_ran(self):
        """Every `$('...')` in every compiled spec, as-is and with a config
        block injected, names a node that runs on every path into its reader."""
        for name, raw in _corpus():
            for config in (False, True):
                with self.subTest(spec=name, config=config):
                    self.assertEqual(_dominance_problems(_file_view(raw, config)), [])


_STRICT_REF = re.compile(r"\$\('((?:[^'\\]|\\.)*)'\)")


def _malformed_refs(workflow):
    """Every parameter string holding a `$(` that does not open a well-formed
    `$('<name>')`: an apostrophe inside a name must be escaped."""
    return [(n["name"], text) for n in workflow["nodes"]
            for text in _strings(n.get("parameters", {}))
            if text.count("$(") != len(_STRICT_REF.findall(text))]


class TestAsciiFoldsTheObject(unittest.TestCase):
    """Curly quotes are folded inside each string before serialising, so the
    written file stays valid JSON and every node reference stays valid."""

    def _curly_spec(self):
        return {
            "title": "The \u201cOwner\u2019s\u201d Intake \u2192 Slack",
            "platform": "n8n",
            "sections": [
                {"key": "in", "label": "1 - CAPTURE",
                 "note": "Every \u201chot\u201d enquiry lands here. The owner\u2019s answers "
                         "get tidied."},
                {"key": "ai", "label": "2 - QUALIFY",
                 "note": "Claude reads the \u201cmessage\u201d and scores it."}],
            "nodes": [
                {"key": "hook", "kind": "trigger.webhook",
                 "label": "1 - The Owner\u2019s \u201cQuote\u201d Form", "section": "in"},
                {"key": "tidy", "kind": "data.transform",
                 "label": "2 - Tidy the Owner's Answers", "section": "in"},
                {"key": "check", "kind": "data.transform",
                 "label": "3 - Check the Owner\u2019s Email", "section": "in"},
                {"key": "ai", "kind": "ai.llm", "label": "4 - Score the \u201cLead\u201d",
                 "section": "ai"},
                {"key": "m", "kind": "ai.model", "app": "anthropic", "label": "Claude",
                 "parent": "ai"},
                {"key": "p", "kind": "ai.parser", "label": "Score", "parent": "ai"},
                {"key": "slack", "kind": "app.action", "app": "slack",
                 "label": "5 - Tell the \u201cSales\u201d Team", "section": "ai"},
                {"key": "ghl", "kind": "net.http", "label": "6 - GHL: Upsert Contact",
                 "section": "ai"}],
            "edges": [{"from": "hook", "to": "tidy"}, {"from": "tidy", "to": "check"},
                      {"from": "check", "to": "ai"}, {"from": "ai", "to": "slack"},
                      {"from": "slack", "to": "ghl"}],
            "input_sample": {"name": "Ayesha \u201cAsh\u201d Khan", "email": "ash@example.org",
                             "message": "I\u2019d like a \u201cdeep\u201d clean"},
            "output_sample": {"score": 82, "reason": "Said \u201cbefore Friday\u201d"},
            "config": {"ghl_api_key": "PASTE-YOUR-GHL-API-KEY"},
        }

    def test_curly_quotes_write_a_valid_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = write_output(generate_from_spec(self._curly_spec()), out_dir=tmp,
                                  copy=False)
            with open(result.path, "r", encoding="utf-8") as fh:
                text = fh.read()
            with open(result.excalidraw_path, "r", encoding="utf-8") as fh:
                json.loads(fh.read())
        text.encode("ascii")  # raises on any non-ASCII character
        workflow = json.loads(text)
        names = {n["name"] for n in workflow["nodes"]}
        self.assertIn("2 - Tidy the Owner's Answers", names)
        self.assertIn('4 - Score the "Lead"', names)
        self.assertEqual(workflow["name"], 'The "Owner\'s" Intake -> Slack')
        # Every reference is a well-formed literal naming a node that ran.
        self.assertEqual(_malformed_refs(workflow), [])
        self.assertEqual(_dominance_problems(workflow), [])
        slack = _node(workflow, "5 - Tell")["parameters"]["text"]
        self.assertIn("$('3 - Check the Owner\\'s Email').item.json.email", slack)
        ghl = json.dumps(_node(workflow, "6 - GHL")["parameters"])
        self.assertIn("$('{}')".format(CONFIG_NODE_NAME), ghl)
        # Embedded JSON (the parser's example) is folded before it is
        # serialised, so it still parses.
        parser = [n for n in workflow["nodes"]
                  if n["type"].endswith("outputParserStructured")][0]
        self.assertEqual(json.loads(parser["parameters"]["jsonSchemaExample"])["reason"],
                         'Said "before Friday"')
        self.assertEqual(workflow["pinData"][next(iter(workflow["pinData"]))][0]["json"]["name"],
                         'Ayesha "Ash" Khan')
        for key in list(workflow["pinData"]) + list(workflow["connections"]):
            self.assertIn(key, names)

    def test_node_ref_escapes_apostrophes_and_backslashes(self):
        expected = "$('2 - Tidy the Owner\\'s Answers')"
        self.assertEqual(node_ref("2 - Tidy the Owner\u2019s Answers"), expected)
        self.assertEqual(node_ref("2 - Tidy the Owner's Answers"), expected)
        self.assertEqual(node_ref("Path a\\b"), "$('Path a\\\\b')")
        self.assertEqual(node_ref("7 \u00b7 Record"), "$('7 - Record')")

    def test_fold_reaches_keys_and_nested_values(self):
        folded = ascii_safe_obj({"7 \u00b7 Log": [{"note": "\u201cok\u201d"}], "n": 3})
        self.assertEqual(folded, {"7 - Log": [{"note": '"ok"'}], "n": 3})
        self.assertEqual(json.loads(json.dumps(folded)), folded)


class TestAppTriggersNeverBorrowCalendly(unittest.TestCase):
    """An app trigger without a catalog entry of its own compiles to a Webhook
    (or the Error Trigger for an error handler), never to calendlyTrigger."""

    def _compile_triggers(self, *triggers):
        nodes = list(triggers) + [dict(_SLACK)]
        edges = [{"from": t["key"], "to": "slack"} for t in triggers]
        return _compile(_base(nodes, edges))

    @staticmethod
    def _trigger(key, label, **extra):
        node = {"key": key, "kind": "trigger.app", "label": label, "section": "in"}
        node.update(extra)
        return node

    def test_facebook_lead_ads(self):
        workflow = self._compile_triggers(
            self._trigger("fb", "1 - Facebook Lead Ad Submitted", app="facebook"))
        node = _node(workflow, "1 - Facebook Lead Ad Submitted")
        self.assertEqual(node["type"], "n8n-nodes-base.facebookLeadAdsTrigger")
        self.assertEqual(node["typeVersion"], 1)
        self.assertEqual(node["parameters"]["event"], "newLead")

    def test_unknown_apps_become_webhooks_with_their_own_paths(self):
        workflow = self._compile_triggers(
            self._trigger("tf", "1 - New Typeform Response", app="typeform", op="new_response"),
            self._trigger("at", "2 - Draft Marked Ready", app="airtable", op="record_updated"),
            self._trigger("pay", "3 - Recurring Payment Succeeded or Failed"))
        paths = []
        for prefix in ("1 - New Typeform", "2 - Draft", "3 - Recurring"):
            node = _node(workflow, prefix)
            self.assertEqual(node["type"], "n8n-nodes-base.webhook", prefix)
            self.assertIn("webhookId", node)
            paths.append(node["parameters"]["path"])
        self.assertEqual(len(set(paths)), 3, paths)
        self.assertNotIn("calendlyTrigger", json.dumps(workflow))

    def test_error_handler_becomes_the_error_trigger(self):
        workflow = self._compile_triggers(
            self._trigger("err", "1 - Any Step in the Scenario Fails", app="make",
                          op="error_handler"))
        self.assertEqual(_node(workflow, "1 - Any Step")["type"], "n8n-nodes-base.errorTrigger")

    def test_a_real_calendly_trigger_stays_calendly(self):
        workflow = self._compile_triggers(
            self._trigger("cal", "1 - Call Booked in Calendly", app="calendly"))
        self.assertEqual(_node(workflow, "1 - Call Booked")["type"],
                         "n8n-nodes-base.calendlyTrigger")

    def test_whole_corpus_calendly_only_for_calendly(self):
        for name, raw in _corpus():
            with self.subTest(spec=name):
                spec = WorkflowSpec.from_dict(copy.deepcopy(raw))
                workflow = compile_n8n(spec)
                names = unique_names([(n.key, n.label) for n in spec.nodes])
                by_name = {n["name"]: n for n in workflow["nodes"]}
                for node in spec.nodes:
                    compiled = by_name[names[node.key]]
                    if compiled["type"].endswith("calendlyTrigger"):
                        self.assertEqual((node.app or "").lower(), "calendly", node.label)


class TestCalendlyActionAndErrorTriggers(unittest.TestCase):
    """Follow-up fixes: a Calendly action is an HTTP Request against the
    Calendly API, and only real error handlers become the Error Trigger."""

    def test_calendly_action_mid_flow_is_http_request(self):
        nodes = [
            {"key": "cal", "kind": "trigger.app", "app": "calendly",
             "label": "1 - Call Booked in Calendly", "section": "in"},
            {"key": "look", "kind": "app.action", "app": "calendly", "op": "get_event",
             "label": "2 - Look Up the Event in Calendly", "section": "ai"},
            dict(_SLACK),
        ]
        edges = [{"from": "cal", "to": "look"}, {"from": "look", "to": "slack"}]
        workflow = _compile(_base(nodes, edges))
        self.assertEqual(_node(workflow, "1 - Call Booked")["type"],
                         "n8n-nodes-base.calendlyTrigger")
        action = _node(workflow, "2 - Look Up")
        self.assertEqual(action["type"], "n8n-nodes-base.httpRequest")
        self.assertIn("Calendly", action["name"])
        self.assertIn("api.calendly.com", json.dumps(action["parameters"]))
        types = [n["type"] for n in workflow["nodes"]]
        self.assertEqual(types.count("n8n-nodes-base.calendlyTrigger"), 1)

    def test_error_trigger_decided_by_app_and_op(self):
        from upwork_gen.spec import Node, is_error_trigger

        def trig(key, label, **extra):
            node = {"key": key, "kind": "trigger.app", "label": label, "section": "in"}
            node.update(extra)
            return node

        cases = [
            (trig("sen", "1 - Sentry Reports a New Error", app="sentry", op="new_error"),
             "n8n-nodes-base.webhook"),
            (trig("pay", "2 - Stripe Payment Error", app="stripe", op="payment_error"),
             "n8n-nodes-base.webhook"),
            (trig("rec", "3 - Recurring Payment Succeeded or Failed", app="stripe",
                  op="invoice_payment"), "n8n-nodes-base.webhook"),
            (trig("n8e", "4 - Any Node Fails", app="n8n", op="error_trigger"),
             "n8n-nodes-base.errorTrigger"),
            (trig("mke", "5 - Any Step in the Scenario Fails", app="make",
                  op="error_handler"), "n8n-nodes-base.errorTrigger"),
        ]
        for raw, expected in cases:
            with self.subTest(label=raw["label"]):
                self.assertEqual(is_error_trigger(Node.from_dict(dict(raw))),
                                 expected.endswith("errorTrigger"))
                workflow = _compile(_base([raw, dict(_SLACK)],
                                          [{"from": raw["key"], "to": "slack"}]))
                node = _node(workflow, raw["label"])
                self.assertEqual(node["name"], raw["label"])
                self.assertEqual(node["type"], expected)
                overview = json.dumps([n["parameters"].get("content", "")
                                       for n in workflow["nodes"]])
                self.assertEqual("Error Workflow" in overview,
                                 expected.endswith("errorTrigger"))

    def test_n8n_app_trigger_is_the_error_trigger_whatever_its_op(self):
        """The catalog's app-level `trigger.app:n8n:` entry is the Error
        Trigger, so an n8n app trigger with no op or a non-error op compiles
        to it; the overview, the Config wiring, the pinned sample and the
        alert text must all treat it as one."""
        from upwork_gen.spec import is_error_trigger

        for op in (None, "on_failure"):
            with self.subTest(op=op):
                err = {"key": "err", "kind": "trigger.app", "app": "n8n",
                       "label": "1 - Any Step Fails", "section": "out"}
                if op is not None:
                    err["op"] = op
                nodes = [
                    err,
                    {"key": "hook", "kind": "trigger.webhook", "label": "2 - New Lead Arrives",
                     "section": "in"},
                    {"key": "crm", "kind": "net.http", "label": "3 - Create the Lead in HubSpot",
                     "section": "in", "params": {"service": "hubspot"}},
                    {"key": "alert", "kind": "app.action", "app": "slack",
                     "label": "4 - Alert the Team", "section": "out"},
                ]
                edges = [{"from": "hook", "to": "crm"}, {"from": "err", "to": "alert"}]
                spec = _base(nodes, edges, config={"slack_channel": "#ops"})
                self.assertTrue(is_error_trigger(spec.node("err")))
                self.assertEqual(spec.entry_node().key, "hook")
                workflow = _compile(spec)
                self.assertEqual(_node(workflow, "1 - Any Step")["type"],
                                 "n8n-nodes-base.errorTrigger")
                overview = " ".join(n["parameters"].get("content", "")
                                    for n in workflow["nodes"]
                                    if n["type"].endswith("stickyNote"))
                self.assertIn("own Error Workflow so 'Any Step Fails' fires", overview)
                into_config = [src for src, ports in workflow["connections"].items()
                               for outs in ports.values() for out in outs for link in out
                               if link["node"] == CONFIG_NODE_NAME]
                self.assertEqual(into_config, ["2 - New Lead Arrives"])
                self.assertNotIn("1 - Any Step Fails", workflow.get("pinData", {}))
                self.assertIn("2 - New Lead Arrives", workflow.get("pinData", {}))
                alert = json.dumps(_node(workflow, "4 - Alert")["parameters"])
                self.assertIn("$json.execution.error.message", alert)

    def test_error_trigger_agrees_with_the_compiler_for_odd_triggers(self):
        """Whatever the compiler emits decides it: an app with a trigger of its
        own stays that trigger with an error op, and a webhook or schedule
        trigger never becomes the Error Trigger."""
        from upwork_gen.spec import is_error_trigger

        cases = [
            ("trigger.app", "calendly", "error_trigger", "n8n-nodes-base.calendlyTrigger"),
            ("trigger.app", "facebook", "error_trigger", None),
            ("trigger.app", "sentry", "error_trigger", "n8n-nodes-base.errorTrigger"),
            ("trigger.app", "N8N", "on_failure", "n8n-nodes-base.webhook"),
            ("trigger.webhook", None, "error_trigger", "n8n-nodes-base.webhook"),
            ("trigger.webhook", "n8n", "on_error", "n8n-nodes-base.webhook"),
            ("trigger.schedule", "n8n", "error_trigger", "n8n-nodes-base.scheduleTrigger"),
        ]
        for kind, app, op, expected in cases:
            with self.subTest(kind=kind, app=app, op=op):
                raw = {"key": "odd", "kind": kind, "op": op,
                       "label": "1 - Something Happens", "section": "in"}
                if app is not None:
                    raw["app"] = app
                spec = _base([raw, dict(_SLACK)], [{"from": "odd", "to": "slack"}])
                workflow = _compile(spec)
                compiled = _node(workflow, "1 - Something")["type"]
                if expected:
                    self.assertEqual(compiled, expected)
                is_err = compiled == "n8n-nodes-base.errorTrigger"
                self.assertEqual(is_error_trigger(spec.node("odd")), is_err)
                overview = json.dumps([n["parameters"].get("content", "")
                                       for n in workflow["nodes"]])
                self.assertEqual("Error Workflow" in overview, is_err)

    def test_whole_corpus_error_trigger_matches_the_compiled_type(self):
        """For every trigger in the vault and every n8n job spec (nested ones
        too), is_error_trigger is exactly "the compiler emitted errorTrigger"."""
        from upwork_gen.spec import is_error_trigger

        corpus = _corpus()
        seen = {name for name, _ in corpus}
        for path in sorted(glob.glob(os.path.join(JOBS_DIR, "**", "spec.json"),
                                     recursive=True)):
            name = os.path.relpath(path, os.path.dirname(ROOT))
            if name in seen:
                continue
            with open(path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
            if raw.get("platform") == "n8n":
                corpus.append((name, raw))
        checked = 0
        for name, raw in corpus:
            spec = WorkflowSpec.from_dict(copy.deepcopy(raw))
            workflow = compile_n8n(spec)
            names = unique_names([(n.key, n.label) for n in spec.nodes])
            by_name = {n["name"]: n for n in workflow["nodes"]}
            for node in spec.flow_nodes:
                if not node.is_trigger:
                    continue
                checked += 1
                with self.subTest(spec=name, node=node.label):
                    compiled = by_name[names[node.key]]["type"]
                    self.assertEqual(is_error_trigger(node),
                                     compiled == "n8n-nodes-base.errorTrigger")
        self.assertGreater(checked, 100)
