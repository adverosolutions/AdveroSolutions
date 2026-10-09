"""Make router route filters built from a spec `condition`."""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from upwork_gen.compile_make import _BOOL_B, compile_make_with_warnings  # noqa: E402
from upwork_gen.spec import WorkflowSpec  # noqa: E402


def walk(flow):
    for module in flow:
        yield module
        for route in module.get("routes") or []:
            for inner in walk(route["flow"]):
                yield inner
        for inner in walk(module.get("onerror") or []):
            yield inner


def _spec(nodes, edges, **extra):
    data = {
        "title": "Acme Lead Desk",
        "platform": "make",
        "sections": [{"key": "in", "label": "1 - Lead Alerts", "note": "New leads land here."}],
        "nodes": nodes,
        "edges": edges,
        "input_sample": {"lead": {"name": "Ana Ruiz", "email": "ana@example.com"},
                         "message": "Need a quote", "odd key": "x"},
        "output_sample": {"ok": True},
    }
    data.update(extra)
    return WorkflowSpec.from_dict(data)


HOOK = {"key": "hook", "kind": "trigger.webhook", "label": "1 - Lead Arrives", "section": "in"}
YES = {"key": "yes", "kind": "app.action", "app": "slack", "op": "post",
       "label": "3a - Post the Lead", "section": "in"}
NO = {"key": "no", "kind": "flow.noop", "label": "3b - Stop Here", "section": "in"}


def _gate(kind="flow.branch", condition=None):
    node = {"key": "gate", "kind": kind, "label": "2 - Real Lead?", "section": "in"}
    if condition is not None:
        node["params"] = {"condition": condition}
    return node


def _edges(yes_label="true", no_label="false", yes_condition=None, no_condition=None):
    yes = {"from": "gate", "to": "yes", "branch": yes_label}
    no = {"from": "gate", "to": "no", "branch": no_label}
    if yes_condition is not None:
        yes["condition"] = yes_condition
    if no_condition is not None:
        no["condition"] = no_condition
    return [{"from": "hook", "to": "gate"}, yes, no]


def _routes(spec):
    blueprint, warnings = compile_make_with_warnings(spec)
    router = [m for m in walk(blueprint["flow"]) if m.get("routes")][0]
    return router, [r["flow"][0].get("filter") for r in router["routes"]], warnings


class TestRouteFilters(unittest.TestCase):
    def test_node_condition_eq_numeric(self):
        cond = {"left": "{{5.statusCode}}", "op": "eq", "right": 200}
        _, filters, warnings = _routes(_spec([HOOK, _gate(condition=cond), YES, NO], _edges()))
        self.assertEqual(filters[0], {"name": "True", "conditions": [[
            {"a": "{{5.statusCode}}", "o": "number:equal", "b": "200"}]]})
        self.assertEqual(filters[1], {"name": "False", "conditions": [[
            {"a": "{{5.statusCode}}", "o": "number:notequal", "b": "200"}]]})
        self.assertFalse([w for w in warnings if "route conditions" in w])

    def test_exists_is_unary(self):
        cond = {"left": "5.data.new", "op": "exists"}
        _, filters, _ = _routes(_spec([HOOK, _gate(condition=cond), YES, NO], _edges()))
        self.assertEqual(filters[0]["conditions"], [[{"a": "{{5.data.new}}", "o": "exist"}]])
        self.assertEqual(filters[1]["conditions"], [[{"a": "{{5.data.new}}", "o": "notexist"}]])

    def test_switch_edge_conditions_hubspot(self):
        edges = _edges("New Order", "Already Synced",
                       {"left": "{{4.data.total}}", "op": "eq", "right": 0},
                       {"left": "{{4.data.total}}", "op": "gt", "right": 0})
        spec = _spec([HOOK, _gate(kind="flow.switch"), YES, NO], edges)
        _, filters, _ = _routes(spec)
        self.assertEqual(filters[0], {"name": "New Order", "conditions": [[
            {"a": "{{4.data.total}}", "o": "number:equal", "b": "0"}]]})
        self.assertEqual(filters[1], {"name": "Already Synced", "conditions": [[
            {"a": "{{4.data.total}}", "o": "number:greater", "b": "0"}]]})
        dumped = [e.to_dict() for e in spec.edges]
        self.assertEqual(dumped[1]["condition"], edges[1]["condition"])
        self.assertNotIn("condition", dumped[0])
        self.assertEqual(WorkflowSpec.from_dict(spec.to_dict()).edges[2].condition,
                         edges[2]["condition"])

    def test_true_op_boolean(self):
        cond = {"left": "{{3.result.is_real_lead}}", "op": "true"}
        _, filters, _ = _routes(_spec([HOOK, _gate(condition=cond), YES, NO],
                                      _edges("real enquiry", "spam")))
        self.assertEqual(filters[0]["conditions"], [[
            {"a": "{{3.result.is_real_lead}}", "o": "boolean:equal", "b": _BOOL_B[True]}]])
        self.assertEqual(filters[1]["conditions"], [[
            {"a": "{{3.result.is_real_lead}}", "o": "boolean:equal", "b": _BOOL_B[False]}]])
        self.assertEqual((_BOOL_B[True], _BOOL_B[False]), ("{{true}}", "{{false}}"))

    def test_no_condition_keeps_stand_in(self):
        router, filters, _ = _routes(_spec([HOOK, _gate(), YES, NO], _edges()))
        stand_in = [[{"a": "{{%s.value}}" % router["id"], "o": "exist"}]]
        self.assertEqual(filters[0], {"name": "True", "conditions": stand_in})
        self.assertEqual(filters[1], {"name": "False", "conditions": stand_in})

    def test_n8n_left_warns_and_falls_back(self):
        cond = {"left": "={{ $json.score }}", "op": "gt", "right": 5}
        router, filters, warnings = _routes(_spec([HOOK, _gate(condition=cond), YES, NO], _edges()))
        stand_in = [[{"a": "{{%s.value}}" % router["id"], "o": "exist"}]]
        self.assertEqual([f["conditions"] for f in filters], [stand_in, stand_in])
        lines = [w for w in warnings if w.startswith("make: route conditions not applied (")]
        self.assertEqual(len(lines), 1)
        self.assertIn("2 - Real Lead?", lines[0])
        self.assertIn("n8n syntax", lines[0])


if __name__ == "__main__":
    unittest.main()
