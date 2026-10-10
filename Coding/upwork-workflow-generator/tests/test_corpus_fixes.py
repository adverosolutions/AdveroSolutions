"""Generator fixes behind the 2026-10-09 corpus failures, each pinned on a
small spec so it holds for future vault entries, not only the ones that
surfaced it.

    python3 -m pytest -q tests/test_corpus_fixes.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from upwork_gen import learn  # noqa: E402
from upwork_gen.compile_excalidraw import compile_excalidraw  # noqa: E402
from upwork_gen.compile_n8n import compile_n8n  # noqa: E402
from upwork_gen.layout import check, layout  # noqa: E402
from upwork_gen.params import CONFIG_NODE_KEY, CONFIG_NODE_NAME  # noqa: E402
from upwork_gen.spec import WorkflowSpec  # noqa: E402

CFG = "$('{}')".format(CONFIG_NODE_NAME)


def _spec(nodes, edges, sections=("in", "out"), **extra):
    raw = {
        "title": "Corpus Fix Build",
        "platform": "n8n",
        "sections": [{"key": k, "label": "{} - {}".format(i + 1, k.upper()), "note": ""}
                     for i, k in enumerate(sections)],
        "nodes": nodes,
        "edges": edges,
        "input_sample": {"email": "a@example.org"},
    }
    raw.update(extra)
    spec = WorkflowSpec.from_dict(raw)
    spec.validate()
    return spec


def _node(workflow, prefix):
    return next(n for n in workflow["nodes"] if n["name"].startswith(prefix))


class TestAuthoredConfigReadOffItsPath(unittest.TestCase):
    """A by-name Config read the author wrote on the error path (which never
    runs through the Config node) gets the value itself, never a reference
    n8n would throw "Referenced node is unexecuted" on."""

    def _spec(self, **extra):
        nodes = [
            {"key": "hook", "kind": "trigger.webhook", "label": "1 - Lead Arrives",
             "section": "in"},
            {"key": "tell", "kind": "app.action", "app": "slack", "label": "2 - Tell Sales",
             "section": "in",
             "params": {"text": "={{ " + CFG + ".item.json.sales_channel }}"}},
            {"key": "err", "kind": "trigger.app", "app": "n8n", "op": "error_trigger",
             "label": "3 - Any Step Fails", "section": "out"},
            {"key": "mail", "kind": "app.action", "app": "gmail", "op": "send",
             "label": "4 - Email You the Error", "section": "out",
             "params": {"sendTo": "={{ " + CFG + ".first().json.alert_email }}",
                        "message": "=Failed at {{ $json.execution.lastNodeExecuted }}, "
                                   "tell {{ " + CFG + ".item.json.alert_email }}"}},
            {"key": "code", "kind": "data.code", "label": "5 - Log the Error",
             "section": "out",
             "params": {"jsCode": "const cfg = " + CFG + ".first().json;\n"
                                  "return [{ json: { to: cfg.alert_email } }];"}},
        ]
        edges = [{"from": "hook", "to": "tell"}, {"from": "err", "to": "mail"},
                 {"from": "mail", "to": "code"}]
        return _spec(nodes, edges, **extra)

    def test_off_path_reads_become_values(self):
        workflow = compile_n8n(self._spec())
        mail = _node(workflow, "4 - Email")["parameters"]
        self.assertEqual(mail["sendTo"], "PASTE-YOUR-ALERT-EMAIL")
        self.assertIn("tell PASTE-YOUR-ALERT-EMAIL", mail["message"])
        self.assertTrue(mail["message"].startswith("=Failed at {{"))
        code = _node(workflow, "5 - Log")["parameters"]["jsCode"]
        self.assertIn('const cfg = {"alert_email": "PASTE-YOUR-ALERT-EMAIL"};', code)
        for name in ("4 - Email", "5 - Log"):
            self.assertNotIn("Config", json.dumps(_node(workflow, name)["parameters"]))
        # The read on the Config node's own path is left as written.
        self.assertIn(CFG + ".item.json.sales_channel",
                      _node(workflow, "2 - Tell")["parameters"]["text"])

    def test_config_holds_only_keys_read_on_its_path(self):
        workflow = compile_n8n(self._spec())
        names = [a["name"] for a in _node(workflow, CONFIG_NODE_NAME)["parameters"]
                 ["assignments"]["assignments"]]
        self.assertEqual(names, ["sales_channel"])
        content = _node(workflow, "Overview")["parameters"]["content"]
        self.assertIn("Fill in alert_email on 'Email You the Error', which runs without the "
                      "Config node.", content)
        self.assertIn("The real values for sales_channel and alert_email.", content)

    def test_a_configured_value_is_used(self):
        workflow = compile_n8n(self._spec(config={"alert_email": "ops@example.org"}))
        self.assertEqual(_node(workflow, "4 - Email")["parameters"]["sendTo"],
                         "ops@example.org")


class TestAuthoredSetListsStayDistinct(unittest.TestCase):
    def test_second_chat_reply_keeps_its_output_and_gains_a_stamp(self):
        reply = lambda key, label, text: {  # noqa: E731
            "key": key, "kind": "data.transform", "label": label, "section": "out",
            "params": {"assignments": {"assignments": [
                {"id": key, "name": "output", "value": text, "type": "string"}]}}}
        nodes = [
            {"key": "chat", "kind": "trigger.chat", "label": "1 - You Ask", "section": "in"},
            {"key": "gate", "kind": "flow.branch", "label": "2 - Answered?", "section": "in"},
            reply("a", "3a - Reply With the Answer", "={{ $json.answer }}"),
            reply("b", "3b - Reply With the Task Number", "=Task {{ $json.id }}"),
        ]
        edges = [{"from": "chat", "to": "gate"},
                 {"from": "gate", "to": "a", "branch": "true"},
                 {"from": "gate", "to": "b", "branch": "false"}]
        workflow = compile_n8n(_spec(nodes, edges))
        first = _node(workflow, "3a")["parameters"]["assignments"]["assignments"]
        second = _node(workflow, "3b")["parameters"]["assignments"]["assignments"]
        self.assertEqual([a["name"] for a in first], ["output"])
        self.assertEqual(second[0], {"id": "b", "name": "output", "value": "=Task {{ $json.id }}",
                                     "type": "string"})
        self.assertEqual([a["name"] for a in second][1], "step")
        self.assertTrue(second[2]["name"].endswith("_at"))


class TestSectionOrderFollowsEdges(unittest.TestCase):
    """A migration path declared after the intake but feeding into it."""

    def _spec(self):
        nodes = [
            {"key": "hook", "kind": "trigger.webhook", "label": "1 - New Lead",
             "section": "intake"},
            {"key": "clean", "kind": "data.code", "label": "2 - Clean the Record",
             "section": "intake"},
            {"key": "push", "kind": "net.http", "label": "3 - Push to the CRM",
             "section": "sync"},
            {"key": "run", "kind": "trigger.webhook", "label": "4 - Run Once: Migrate",
             "section": "migrate"},
            {"key": "pull", "kind": "net.http", "label": "5 - Pull the Old Records",
             "section": "migrate"},
        ]
        edges = [{"from": "hook", "to": "clean"}, {"from": "clean", "to": "push"},
                 {"from": "run", "to": "pull"}, {"from": "pull", "to": "clean"}]
        return _spec(nodes, edges, sections=("intake", "sync", "migrate"))

    def test_bands_never_overlap(self):
        spec = self._spec()
        placement = layout(spec)
        self.assertEqual(check(spec, placement), [])
        x = {s.key: s.x for s in placement.stickies}
        self.assertLess(x["migrate"], x["intake"])
        self.assertLess(x["intake"], x["sync"])

    def test_agreeing_order_is_unchanged(self):
        spec = self._spec()
        spec.edges = [e for e in spec.edges if e.src != "pull"]
        x = {s.key: s.x for s in layout(spec).stickies}
        self.assertLess(x["intake"], x["sync"])
        self.assertLess(x["sync"], x["migrate"])


class TestDiagramLeavesOutAnAuthoredConfigNode(unittest.TestCase):
    def test_config_node_is_bridged(self):
        nodes = [
            {"key": "hook", "kind": "trigger.webhook", "label": "1 - New Lead", "section": "in"},
            {"key": CONFIG_NODE_KEY, "kind": "data.transform", "label": CONFIG_NODE_NAME,
             "section": "in"},
            {"key": "clean", "kind": "data.code", "label": "2 - Clean the Record",
             "section": "out"},
        ]
        edges = [{"from": "hook", "to": CONFIG_NODE_KEY}, {"from": CONFIG_NODE_KEY, "to": "clean"}]
        dsl = compile_excalidraw(_spec(nodes, edges))
        self.assertNotIn("Config", dsl)
        self.assertIn("(1 - New Lead) -> [2 - Clean the Record]", dsl)


class TestRepromotingAPosting(unittest.TestCase):
    """One posting often yields several different archetypes (separate job
    folders). Sharing the `url:` line alone never merges them; a retitled
    rebuild reuses an earlier archetype only on evidence it is that build."""

    POST = ("url: https://www.upwork.com/jobs/~01example\nGlazier Quote Follow-Ups\n"
            "Hourly, intermediate.\n\nWe are a glazier shop and want quote follow-ups "
            "for windshield and storefront glass jobs, plus a reception bot for walk-ins.\n")

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name
        self.saved = (learn.VAULT_DIR, learn.KEYWORDS_PATH)
        learn.VAULT_DIR = os.path.join(self.tmp, "archetypes")
        learn.KEYWORDS_PATH = os.path.join(self.tmp, "keywords.json")
        os.makedirs(os.path.join(self.tmp, "sources"))

    def tearDown(self):
        learn.VAULT_DIR, learn.KEYWORDS_PATH = self.saved
        self._tmp.cleanup()

    @staticmethod
    def _spec(title, label="1 - Quote Sent"):
        return _spec([{"key": "hook", "kind": "trigger.webhook", "label": label,
                       "section": "in"}], [], sections=("in",), title=title)

    def _promote(self, spec, job_dir=None):
        report = learn.promote(spec, job_text=self.POST, job_dir=job_dir)
        source = os.path.join(self.tmp, "sources", report["archetype"] + ".txt")
        if not os.path.exists(source):  # what maintain.archive_source keeps
            with open(source, "w", encoding="utf-8") as fh:
                fh.write(self.POST)
        return report

    def _vault(self, archetype_id):
        with open(os.path.join(learn.VAULT_DIR, archetype_id + ".json"), encoding="utf-8") as fh:
            return json.load(fh)

    def test_two_builds_of_one_posting_stay_apart(self):
        quotes = self._promote(self._spec("Glazier Quote Follow-Ups"))
        desk = self._promote(self._spec("Your Walk-In Reception Bot", "1 - Customer Walks In"))
        self.assertNotEqual(quotes["archetype"], desk["archetype"])
        for rebuilt, other in ((quotes, desk), (desk, quotes)):
            before = self._vault(other["archetype"])
            title = self._vault(rebuilt["archetype"])["title"]
            again = self._promote(self._spec(title, "1 - Rebuilt"))
            self.assertEqual(again["archetype"], rebuilt["archetype"])
            self.assertEqual(self._vault(other["archetype"]), before)
        # A new title with no evidence is a new archetype, as before.
        third = self._promote(self._spec("Glass Invoice Reminders", "1 - Invoice Due"))
        self.assertNotIn(third["archetype"], (quotes["archetype"], desk["archetype"]))
        self.assertEqual(len(learn.load_learned()), 3)

    def test_retired_title_in_stale_is_reused(self):
        first = self._promote(self._spec("Square, Zapier and Monday: Wedding Cake "
                                         "Consultations and Deliveries"))
        sibling = self._promote(self._spec("Your Bakery Delivery Board", "1 - Order Paid"))
        job = os.path.join(self.tmp, "job")
        os.makedirs(os.path.join(job, ".stale"))
        open(os.path.join(job, ".stale", "square-zapier-and-monday-wedding-cake-"
                          "consultations-and-deli.excalidraw"), "w").close()
        retitled = self._spec("Your Wedding Cake Orders, Step by Step", "1 - Enquiry In")
        without = learn.earlier_version_of(retitled, self.POST)
        again = self._promote(retitled, job_dir=job)
        self.assertIsNone(without)
        self.assertEqual(again["archetype"], first["archetype"])
        self.assertTrue(again["replaced"])
        self.assertEqual(self._vault(first["archetype"])["title"],
                         "Your Wedding Cake Orders, Step by Step")
        self.assertEqual(self._vault(sibling["archetype"])["title"], "Your Bakery Delivery Board")
        # Once folded, a rebuild under that title finds it by title alone.
        once_more = self._promote(self._spec("Your Wedding Cake Orders, Step by Step"))
        self.assertEqual(once_more["archetype"], first["archetype"])
        self.assertEqual(len(learn.load_learned()), 2)


if __name__ == "__main__":
    unittest.main()
