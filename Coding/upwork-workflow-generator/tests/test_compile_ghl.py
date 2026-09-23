"""GoHighLevel import compiler: shapes, graph integrity, multi-workflow split.

Shapes that appear in reference/ghl_export_sales_request_follow_up.json (a real
export) are checked key for key against it; the rest are research shapes and
are only checked for the fields the field report showed missing.

    python3 -m pytest -q tests/test_compile_ghl.py
"""

from __future__ import annotations

import copy
import json
import os
import sys
import tempfile
import unittest
import uuid
import warnings

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from upwork_gen.compile_ghl import (WAIT_UNITS, GHLCompileWarning, compile_ghl,  # noqa: E402
                                    compile_ghl_many, main as compile_ghl_main, split_ghl_spec)
from upwork_gen.compile_ghl_prompt import OPS, TRIGGER_OPS, _node_op  # noqa: E402
from upwork_gen.spec import SpecError, WorkflowSpec  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOC = "ebyNANPagaK7ycf1pfge"
IDS = json.load(open(os.path.join(ROOT, "upwork_gen", "catalog", "ghl_ids_{}.json".format(LOC))))
EXPORT = json.load(open(os.path.join(ROOT, "reference", "ghl_export_sales_request_follow_up.json")))
# examples/ghl_reference_all_types.json after import into a Draft, a hand check that
# re-added the broken steps, Save, and export (2026-09-23, captured 04:51).
EXPORT_ALL = json.load(open(os.path.join(ROOT, "reference", "ghl_export_reference_all_types.json")))
REFERENCE_SPEC = os.path.join(ROOT, "examples", "ghl_reference_all_types.json")
CHECKLIST = os.path.join(ROOT, "reference", "GHL_REFERENCE_CHECKLIST.md")
SALES_WF = "591d527e-70b3-4f96-9e19-ddc542ebc48d"
CALCOM_SPEC = os.path.join(os.path.dirname(ROOT), "upwork-pipeline", "jobs",
                           "cal-com-ghl-call-booked-pipeline", "spec.json")


def _load(path):
    return WorkflowSpec.load(path)


def _compile(path):
    # The reference spec warns on purpose (Go To into the other branch, Assign to
    # user with no user); the warning tests check those. Silence them here.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", GHLCompileWarning)
        return compile_ghl(_load(path), IDS, LOC)


def _by_name(wf, name):
    hits = [n for n in wf["nodes"] if n["name"] == name]
    assert hits, "no node named {!r}".format(name)
    return hits[0]


def _is_uuid4(value):
    try:
        return uuid.UUID(value).version == 4 and str(uuid.UUID(value)) == value
    except (ValueError, TypeError, AttributeError):
        return False


def normalize_ids(wf):
    """The workflow with every per-compile value (generated ids, timestamps)
    replaced by a placeholder numbered in order of first appearance, so two
    compiles of one spec compare equal exactly when their structure does."""
    gen = {wf["workflowId"]}
    gen.update(n["id"] for n in wf["nodes"])
    gen.update(t["id"] for t in wf["triggers"])
    for n in wf["nodes"]:
        if n["type"] == "workflow_goal":
            gen.update(c["id"] for seg in n["attributes"]["segments"] for c in seg["conditions"])
    names = {}
    stamps = {"capturedAt", "createdAt", "updatedAt", "date_added", "date_updated"}

    def sub(v):
        if v in gen:
            return names.setdefault(v, "<id-{}>".format(len(names)))
        return v.replace(wf["workflowId"], sub(wf["workflowId"])) if wf["workflowId"] in v else v

    def walk(v, key=None):
        if isinstance(v, dict):
            return {sub(k): walk(x, k) for k, x in v.items()}
        if isinstance(v, list):
            return [walk(x) for x in v]
        if isinstance(v, str):
            return "<ts>" if key in stamps else sub(v)
        return v
    return walk(wf)


def _export_nodes(pred):
    return [n for n in EXPORT["nodes"] if pred(n)]


def _mini(nodes, edges, title="Mini"):
    return WorkflowSpec.from_dict({"title": title, "platform": "gohighlevel", "nodes": nodes, "edges": edges})


def _tag_trigger(key, tag, label=None):
    return {"key": key, "kind": "trigger.app", "app": "ghl", "op": "contact_tag_added",
            "label": label or "Tag {} added".format(tag), "params": {"tag": tag}}


def _sms(key, label=None):
    return {"key": key, "kind": "app.action", "app": "ghl", "op": "send_sms",
            "label": label or "Text {}".format(key), "params": {"message": "hi from {}".format(key)}}


class GraphChecks:
    """Invariants every compiled workflow must satisfy."""

    def assert_graph_ok(self, wf):
        nodes = wf["nodes"]
        ids = [n["id"] for n in nodes]
        self.assertEqual(len(ids), len(set(ids)), "duplicate node ids")
        idset = set(ids)
        for n in nodes:
            self.assertTrue(_is_uuid4(n["id"]), "node id not a uuid4: {!r}".format(n["id"]))
            nxt = n.get("next", "")
            targets = nxt if isinstance(nxt, list) else ([nxt] if nxt else [])
            for t in targets:
                self.assertIn(t, idset, "{} -> dangling next {}".format(n["name"], t))
            for key in ("parentKey", "parent"):
                if key in n:
                    self.assertIn(n[key], idset, "{} -> dangling {} {}".format(n["name"], key, n[key]))
            for s in n.get("sibling", []):
                self.assertIn(s, idset)
            if n["type"] == "workflow_goal":
                for seg in n["attributes"]["segments"]:
                    for c in seg["conditions"]:
                        self.assertTrue(_is_uuid4(c["id"]))
            if n.get("nodeType") == "condition-node":
                for b in n["attributes"]["branches"]:
                    self.assertIn(b["id"], idset)
            if n["type"] == "wait":
                self.assertIn(n["attributes"]["startAfter"]["type"], WAIT_UNITS)
            if n["type"] == "goto" and n["attributes"].get("targetNodeId"):
                self.assertIn(n["attributes"]["targetNodeId"], idset)
        # every node except the first is somebody's next
        pointed = set()
        for n in nodes:
            nxt = n.get("next", "")
            pointed.update(nxt if isinstance(nxt, list) else ([nxt] if nxt else []))
        roots = [n["name"] for n in nodes if n["id"] not in pointed]
        self.assertEqual(len(roots), 1, "expected one chain root, got {}".format(roots))
        self.assertTrue(_is_uuid4(wf["workflowId"]))


class TestReferenceSpec(unittest.TestCase, GraphChecks):
    @classmethod
    def setUpClass(cls):
        cls.wf, cls.unresolved = _compile(REFERENCE_SPEC)

    def test_graph(self):
        self.assert_graph_ok(self.wf)

    def test_every_emitted_op_is_present(self):
        types = {n["type"] for n in self.wf["nodes"]}
        for t in ("add_contact_tag", "remove_contact_tag", "sms", "email", "wait", "create_opportunity",
                  "internal_update_opportunity", "internal_notification", "task-notification", "add_notes",
                  "call", "update_contact_field", "assign_user", "webhook", "chatgpt",
                  "add_to_workflow", "remove_from_workflow", "review_request", "workflow_goal",
                  "if_else", "goto"):
            self.assertIn(t, types)
        kinds = {n["attributes"]["type"] for n in self.wf["nodes"] if n["type"] == "internal_notification"}
        self.assertEqual(kinds, {"sms", "email", "notification"})
        units = {n["attributes"]["startAfter"]["type"] for n in self.wf["nodes"] if n["type"] == "wait"}
        self.assertEqual(units, {"days", "hour"})

    def test_triggers_have_tag_filters(self):
        added, removed = self.wf["triggers"]
        self.assertEqual(added["type"], "contact_tag")
        self.assertEqual(added["conditions"][0]["field"], "tagsAdded")
        self.assertEqual(added["conditions"][0]["value"], "call-booked")
        self.assertEqual(removed["conditions"][0]["field"], "tagsRemoved")
        self.assertEqual(removed["conditions"][0]["value"], "call-cancelled")

    def test_if_else_tag_condition(self):
        cond = _by_name(self.wf, "If Else Has Tag call-booked")
        c = cond["attributes"]["branches"][0]["segments"][0]["conditions"][0]
        self.assertEqual((c["conditionType"], c["conditionSubType"], c["conditionOperator"]),
                         ("contact_detail", "tags", "index-of-true"))
        self.assertEqual(c["conditionValue"], ["call-booked"])
        kinds = sorted(n["nodeType"] for n in self.wf["nodes"] if n.get("parent") == cond["id"])
        self.assertEqual(kinds, ["branch-no", "branch-yes"])

    def test_go_to_resolves_and_end_emits_nothing(self):
        goto = [n for n in self.wf["nodes"] if n["type"] == "goto"][0]
        target = _by_name(self.wf, "No Branch Send SMS Last Step")
        self.assertEqual(goto["attributes"]["targetNodeId"], target["id"])
        self.assertEqual(target["next"], "")
        self.assertFalse([n for n in self.wf["nodes"] if "End Nothing" in n["name"]])

    def test_every_action_op_is_in_the_reference_spec(self):
        spec = _load(REFERENCE_SPEC)
        used = {_node_op(n) for n in spec.nodes}
        self.assertEqual(set(OPS) - TRIGGER_OPS - used, set())

    def test_every_reference_resolves(self):
        self.assertEqual(self.unresolved, [])
        for typ in ("add_to_workflow", "remove_from_workflow"):
            (node,) = [n for n in self.wf["nodes"] if n["type"] == typ]
            self.assertEqual(node["attributes"]["workflow_id"], SALES_WF)
            self.assertEqual(node["attributes"]["workflow_name"], "Your Sales Request Follow-Up System")
        self.assertEqual(IDS["workflow:Your Sales Request Follow-Up System"], SALES_WF)

    def test_checklist_has_a_row_per_step_and_the_safety_lines(self):
        text = open(CHECKLIST, encoding="utf-8").read()
        rows = [ln for ln in text.splitlines() if ln.startswith("| ") and not ln.startswith("| Step")]
        spec = _load(REFERENCE_SPEC)
        for n in spec.nodes:
            num, rest = n.label.split(" - ", 1)
            want = "| {} {} |".format(num, rest)
            self.assertEqual(sum(1 for r in rows if r.startswith(want)), 1, want)
        self.assertEqual(len(rows), len(spec.nodes))
        head = text.split("| Step")[0]
        for phrase in ("NEW workflow", "Draft", "Never publish", "call-booked", "call-cancelled",
                       "python3 -m upwork_gen.compile_ghl examples/ghl_reference_all_types.json "
                       "~/Desktop/GHL-Imports/REFERENCE-all-step-types.ghl.json",
                       "out of scope for this pass", "UNVERIFIED"):
            self.assertIn(phrase, head)
        self.assertLess(text.index("Never publish"), text.index("File:"))
        for trig in ("T1", "T2"):
            (row,) = [r for r in rows if r.startswith("| {} ".format(trig))]
            self.assertIn("If the trigger itself is missing after import, add it by hand", row)

    def test_rebuild_command_matches_a_fresh_compile(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "ref.ghl.json")
            self.assertEqual(compile_ghl_main([REFERENCE_SPEC, out]), 0)
            built = json.load(open(out))
        self.assertEqual(normalize_ids(built), normalize_ids(self.wf))
        self.assertNotEqual(built["workflowId"], self.wf["workflowId"])

    def test_rebuild_command_writes_valid_json_for_curly_quotes(self):
        """main() writes generate.ascii_json (each string folded before it is
        serialised). Folding the serialised text turned a curly double quote
        into a bare `"` inside a JSON string, so the file did not load."""
        spec = {"title": "Curly \u201cQuotes\u201d Check", "platform": "gohighlevel", "nodes": [
            _tag_trigger("t", "hot", "Tag \u201chot\u201d Added"),
            {"key": "a", "kind": "app.action", "app": "ghl", "op": "send_sms",
             "label": "Text the Lead\u2019s \u201cOwner\u201d", "params": {"message": "It\u2019s \u201cbooked\u201d"}}],
            "edges": [{"from": "t", "to": "a"}]}
        with tempfile.TemporaryDirectory() as tmp:
            src, out = os.path.join(tmp, "spec.json"), os.path.join(tmp, "curly.ghl.json")
            with open(src, "w", encoding="utf-8") as fh:
                json.dump(spec, fh, ensure_ascii=False)
            self.assertEqual(compile_ghl_main([src, out]), 0)
            with open(out, encoding="utf-8") as fh:
                text = fh.read()
        wf = json.loads(text)
        self.assertTrue(all(ord(c) < 128 for c in text))
        self.assertEqual(wf["workflowName"], 'Curly "Quotes" Check')
        self.assertEqual(wf["triggers"][0]["name"], 'Tag "hot" Added')
        self.assertEqual([n["name"] for n in wf["nodes"]], ['Text the Lead\'s "Owner"'])
        self.assertEqual(wf["nodes"][0]["attributes"]["body"], 'It\'s "booked"')


@unittest.skipUnless(os.path.exists(CALCOM_SPEC), "Cal.com job spec not on this machine")
class TestCalComSpec(unittest.TestCase, GraphChecks):
    """The spec that was imported into GHL on 2026-09-22; fixes for its three problems."""

    @classmethod
    def setUpClass(cls):
        cls.wf, cls.unresolved = _compile(CALCOM_SPEC)

    def test_graph_and_ids_resolved(self):
        self.assert_graph_ok(self.wf)
        self.assertEqual(self.unresolved, [])
        self.assertEqual(len(self.wf["nodes"]), 12)

    def test_trigger_has_tag_added_filter(self):
        (t,) = self.wf["triggers"]
        self.assertEqual(t["type"], "contact_tag")
        self.assertEqual(t["conditions"], [{"field": "tagsAdded", "operator": "index-of-true",
                                            "value": "call-booked", "title": "Tag Added",
                                            "type": "select", "id": "tag-added"}])

    def test_goal_uses_add_contact_tag(self):
        goal = _by_name(self.wf, "Goal: Call Cancelled in Cal.com")
        cond = goal["attributes"]["segments"][0]["conditions"][0]
        self.assertEqual(cond["goal_condition"], "add_contact_tag")
        self.assertEqual(cond["extras"], {"tags": ["call-cancelled"]})

    def test_task_is_task_notification(self):
        task = _by_name(self.wf, "Task: Close Out the Card After the Call")
        self.assertEqual(task["type"], "task-notification")
        self.assertEqual(task["attributes"]["type"], "task_notification")
        self.assertTrue(task["attributes"]["title"].startswith("Move {{contact.first_name}}"))
        self.assertIn("body", task["attributes"])

    def test_update_opportunity_type_and_ids(self):
        upd = _by_name(self.wf, "Move the Opportunity to Cancelled")
        self.assertEqual(upd["type"], "internal_update_opportunity")
        self.assertEqual(upd["workflowsActionType"], "INTERNAL")
        a = upd["attributes"]
        self.assertEqual(a["pipelineId"], IDS["pipeline:Call Booked Pipeline"])
        self.assertEqual(a["__customInputFields__"][0]["filterField"], "pipelineStageId")
        self.assertEqual(a["__customInputFields__"][0]["value"], IDS["stage:Call Booked Pipeline/Cancelled"])
        self.assertTrue(a["allowBackward"])
        self.assertEqual((a["pipeline_name"], a["pipeline_stage_name"]), ("Call Booked Pipeline", "Cancelled"))

    def test_create_opportunity_ids(self):
        opp = _by_name(self.wf, "Add the Lead to Call Booked Pipeline")
        self.assertEqual(opp["attributes"]["pipeline_id"], IDS["pipeline:Call Booked Pipeline"])
        self.assertEqual(opp["attributes"]["pipeline_stage_id"], IDS["stage:Call Booked Pipeline/Call Booked"])

    def test_email_has_html_and_body(self):
        em = _by_name(self.wf, "Email the Lead One Prep Question")
        self.assertEqual(em["attributes"]["html"], em["attributes"]["body"])


class TestShapesMatchRealExport(unittest.TestCase):
    """For every op the real export shows, our attribute keys match its keys."""

    @classmethod
    def setUpClass(cls):
        cls.wf, _ = _compile(REFERENCE_SPEC)

    def _ours(self, pred):
        hits = [n for n in self.wf["nodes"] if pred(n)]
        self.assertTrue(hits)
        return hits[0]

    def _same_keys(self, pred, superset=False):
        theirs = _export_nodes(pred)[0]
        ours = self._ours(pred)
        if superset:
            self.assertTrue(set(theirs["attributes"]) <= set(ours["attributes"]),
                            "missing {}".format(set(theirs["attributes"]) - set(ours["attributes"])))
        else:
            self.assertEqual(set(ours["attributes"]), set(theirs["attributes"]))
        extra_node_keys = {"nextName", "parentKeyName", "parentName", "siblingNames", "nextNames"}
        self.assertTrue(set(theirs) - extra_node_keys - {"next", "parent", "parentKey", "sibling"}
                        <= set(ours), "node-level keys missing: {}".format(set(theirs) - set(ours)))
        return theirs, ours

    def test_tags(self):
        self._same_keys(lambda n: n["type"] == "add_contact_tag")
        self._same_keys(lambda n: n["type"] == "remove_contact_tag")

    def test_sms(self):
        self._same_keys(lambda n: n["type"] == "sms")

    def test_email_keeps_export_keys_plus_body(self):
        theirs, ours = self._same_keys(lambda n: n["type"] == "email", superset=True)
        self.assertEqual(set(ours["attributes"]) - set(theirs["attributes"]), {"body"})

    def test_wait(self):
        theirs, ours = self._same_keys(lambda n: n["type"] == "wait")
        self.assertEqual(set(ours["attributes"]["startAfter"]), set(theirs["attributes"]["startAfter"]))

    def test_create_opportunity(self):
        self._same_keys(lambda n: n["type"] == "create_opportunity")

    def test_call(self):
        self._same_keys(lambda n: n["type"] == "call")

    def test_manual_action_is_add_notes(self):
        self._same_keys(lambda n: n["type"] == "add_notes")

    def test_update_opportunity_keeps_export_keys(self):
        self._same_keys(lambda n: n["type"] == "internal_update_opportunity", superset=True)

    def test_internal_notification_in_app(self):
        pred = lambda n: n["type"] == "internal_notification" and n["attributes"]["type"] == "notification"  # noqa: E731
        theirs, ours = self._same_keys(pred)
        self.assertEqual(set(ours["attributes"]["notification"]), set(theirs["attributes"]["notification"]))

    def test_internal_notification_other_variants_keep_outer_keys(self):
        theirs = _export_nodes(lambda n: n["type"] == "internal_notification")[0]
        for kind in ("sms", "email"):
            ours = self._ours(lambda n: n["type"] == "internal_notification" and n["attributes"]["type"] == kind)
            self.assertEqual(set(ours["attributes"]), set(theirs["attributes"]))
            self.assertIsInstance(ours["attributes"][kind], dict)

    def test_goal_top_level(self):
        theirs, ours = self._same_keys(lambda n: n["type"] == "workflow_goal")
        self.assertEqual(set(ours["attributes"]["segments"][0]["conditions"][0]),
                         set(theirs["attributes"]["segments"][0]["conditions"][0]))

    def test_if_else_parent_and_branches(self):
        cond = lambda n: n.get("nodeType") == "condition-node"  # noqa: E731
        theirs, ours = self._same_keys(cond)
        self.assertEqual(set(ours["attributes"]["branches"][0]), set(theirs["attributes"]["branches"][0]))
        self.assertEqual(set(ours["attributes"]["branches"][0]["segments"][0]),
                         set(theirs["attributes"]["branches"][0]["segments"][0]))
        self.assertTrue(set(ours["attributes"]["branches"][0]["segments"][0]["conditions"][0])
                        <= set(theirs["attributes"]["branches"][0]["segments"][0]["conditions"][1]))
        self._same_keys(lambda n: n.get("nodeType") == "branch-yes")
        self._same_keys(lambda n: n.get("nodeType") == "branch-no")

    def test_trigger_keys(self):
        self.assertEqual(set(self.wf["triggers"][0]), set(EXPORT["triggers"][0]))
        self.assertTrue(set(EXPORT) <= set(self.wf))


def _is_annotation_of(name_key, src_key):
    """Port of the extension's lib/importer.js isAnnotationOf: True when
    `name_key` is the *Name / *_name mirror its exporter adds next to
    `src_key` (pipelineId -> pipelineName, value -> valueName,
    pipeline_id -> pipeline_name, tags -> tagsNames). Its importer strips
    these before writing, so they are not part of any shape."""
    if not (name_key.endswith("Name") or name_key.endswith("Names") or name_key.endswith("_name")):
        return False
    if src_key.endswith("Id"):
        return name_key in (src_key[:-2] + "Name", src_key + "Name")
    if src_key.endswith("_id"):
        return name_key == src_key[:-3] + "_name"
    if src_key == "value":
        return name_key == "valueName"
    if src_key.endswith("s"):
        return name_key == src_key + "Names"
    return name_key == src_key + "Name"


def _strip_annotations(value):
    """Port of lib/importer.js stripAnnotations, on a copy."""
    if isinstance(value, list):
        return [_strip_annotations(v) for v in value]
    if not isinstance(value, dict):
        return value
    keys = list(value)
    out = {}
    for nk in keys:
        base = nk[:-1] if nk.endswith("Names") else nk
        paired = any(sk != nk and (_is_annotation_of(nk, sk) or
                                   (nk.endswith("Names") and _is_annotation_of(base, sk)))
                     for sk in keys)
        if not paired:
            out[nk] = _strip_annotations(value[nk])
    return out


def _shape(value):
    """Key sets and value types, recursively; no values."""
    if isinstance(value, dict):
        return {k: _shape(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_shape(v) for v in value]
    return type(value).__name__


def _generated_ids(wf):
    """Every id a compile (or GHL, on import) makes up: workflow, nodes,
    triggers, goal conditions."""
    gen = {wf["workflowId"]}
    gen.update(n["id"] for n in wf["nodes"])
    gen.update(t["id"] for t in wf["triggers"])
    for n in wf["nodes"]:
        if n["type"] == "workflow_goal":
            gen.update(c["id"] for seg in n["attributes"]["segments"] for c in seg["conditions"])
    return gen


def _mask(value, gen):
    if isinstance(value, dict):
        return {k: _mask(v, gen) for k, v in value.items()}
    if isinstance(value, list):
        return [_mask(v, gen) for v in value]
    return "<id>" if isinstance(value, str) and value in gen else value


# Node-level keys that are linkage (compared by name below) or exporter mirrors.
_LINK_KEYS = {"id", "next", "parentKey", "parent", "sibling",
              "nextName", "nextNames", "parentKeyName", "parentName", "siblingNames"}
# Trigger keys GHL (schedule_config) or the exporter (location_name, the mirror of
# location_id) adds on export. Neither is needed for import: these triggers were
# written without them and GHL kept them.
_TRIGGER_EXPORT_ONLY = {"schedule_config", "location_name"}

# What Lorenzo typed or picked by hand in GHL, applied to a copy of the reference
# spec so the compile can be compared value for value. Labels: GHL names a step
# added by hand after its type, and he renamed step 19.
_HAND_EDIT_LABELS = {"s18": "18 - GPT powered by OpenAI",
                     "s19": "19 - Add to Workflow Your Sales Request Follow-Up",
                     "s21": "21 - Send review request"}
_HAND_EDIT_PARAMS = {"s15": {"value": "e"},          # the value he typed into Call Notes
                     "s16": {"user": "Lorenzo Villarreal"}}  # the user he picked
# GHL defaults the compiler deliberately does not emit (the panel works without
# them, see compile_ghl._attrs): dropped from the export side before comparing.
_NOT_ADOPTED = {"Add Task Due in 1 Day": {"attributes": ["__customInputs__"]},
                "Manual Action Call as Add Note": {"attributes": ["type"]},
                "Add to Workflow Your Sales Request Follow-Up": {"attributes": ["input_trigger_params", "type"]}}
# A value GHL filled in where the compiler keeps its own (GHL's own 2026-09-21
# export has color null): dropped from both sides.
_OWN_DEFAULT = {"Manual Action Call as Add Note": ["color"]}


def _hand_edited_reference():
    """(spec, ids) for the reference spec with Lorenzo's hand edits. The user id
    comes from the export itself, as a `user:<name>` id-map entry: the compiler
    never carries a location's user id."""
    d = json.load(open(REFERENCE_SPEC))
    for n in d["nodes"]:
        if n["key"] in _HAND_EDIT_LABELS:
            n["label"] = _HAND_EDIT_LABELS[n["key"]]
        n["params"].update(_HAND_EDIT_PARAMS.get(n["key"], {}))
    (assign,) = [n for n in EXPORT_ALL["nodes"] if n["type"] == "assign_user"]
    ids = dict(IDS)
    ids["user:{}".format(assign["attributes"]["user_listNames"][0])] = assign["attributes"]["user_list"][0]
    return WorkflowSpec.from_dict(d), ids


def _export_side(node):
    n = copy.deepcopy(node)
    for key in _NOT_ADOPTED.get(n["name"], {}).get("attributes", []):
        del n["attributes"][key]
    for key in _OWN_DEFAULT.get(n["name"], []):
        del n["attributes"][key]
    return n


def _our_side(node):
    n = copy.deepcopy(node)
    for key in _OWN_DEFAULT.get(n["name"], []):
        del n["attributes"][key]
    return n


class TestReferenceExportLock(unittest.TestCase):
    """examples/ghl_reference_all_types.json (with Lorenzo's hand edits, see
    _HAND_EDIT_*) compiled today against reference/ghl_export_reference_all_types.json,
    the saved export after his hand check: every step and trigger, matched by
    order and name, has the same type, node-level keys, attribute keys and
    value shapes, attribute values (generated ids masked, exporter *Name
    mirrors stripped, the declared _NOT_ADOPTED / _OWN_DEFAULT keys left out)
    and linkage. Timestamps and capture metadata are ignored. The one known
    divergence is the Go To target (masked as an id): the spec's step 27,
    GHL's default step 01."""

    @classmethod
    def setUpClass(cls):
        spec, ids = _hand_edited_reference()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", GHLCompileWarning)
            cls.wf, cls.unresolved = compile_ghl(spec, ids, LOC)
        cls.warned = [str(w.message) for w in caught if issubclass(w.category, GHLCompileWarning)]
        cls.ours_gen = _generated_ids(cls.wf)
        cls.theirs_gen = _generated_ids(EXPORT_ALL)
        cls.pairs = [(_our_side(o), _export_side(t)) for o, t in zip(cls.wf["nodes"], EXPORT_ALL["nodes"])]

    def test_same_steps_in_the_same_order(self):
        self.assertEqual([n["name"] for n in self.wf["nodes"]], [n["name"] for n in EXPORT_ALL["nodes"]])
        self.assertEqual(len(EXPORT_ALL["nodes"]), 29)
        self.assertEqual(self.unresolved, [])

    def test_declared_leave_outs_exist_in_the_export(self):
        by_name = {n["name"]: n for n in EXPORT_ALL["nodes"]}
        for name, keys in _NOT_ADOPTED.items():
            for k in keys["attributes"]:
                self.assertIn(k, by_name[name]["attributes"], name)
        for name, keys in _OWN_DEFAULT.items():
            for k in keys:
                self.assertIn(k, by_name[name]["attributes"], name)

    def test_every_step_type_and_node_keys(self):
        for ours, theirs in self.pairs:
            with self.subTest(step=ours["name"]):
                self.assertEqual(ours["type"], theirs["type"])
                o = {k: v for k, v in ours.items() if k not in _LINK_KEYS and k != "attributes"}
                t = {k: v for k, v in theirs.items() if k not in _LINK_KEYS and k != "attributes"}
                self.assertEqual(o, t)  # type, name, order, nodeType, cat, workflowsActionType, stepIndex

    def test_every_step_attribute_keys_and_shapes(self):
        for ours, theirs in self.pairs:
            with self.subTest(step=ours["name"]):
                self.assertEqual(_shape(_strip_annotations(ours["attributes"])),
                                 _shape(_strip_annotations(theirs["attributes"])))

    def test_every_step_attribute_values_with_ids_masked(self):
        for ours, theirs in self.pairs:
            with self.subTest(step=ours["name"]):
                self.assertEqual(_mask(_strip_annotations(ours["attributes"]), self.ours_gen),
                                 _mask(_strip_annotations(theirs["attributes"]), self.theirs_gen))

    def test_linkage_by_name(self):
        def links(wf):
            name = {n["id"]: n["name"] for n in wf["nodes"]}
            out = []
            for n in wf["nodes"]:
                nxt = n.get("next", "")
                out.append((n["name"],
                            [name[x] for x in nxt] if isinstance(nxt, list) else name.get(nxt, nxt),
                            name.get(n.get("parentKey")), name.get(n.get("parent")),
                            [name[x] for x in n.get("sibling", [])]))
            return out
        self.assertEqual(links(self.wf), links(EXPORT_ALL))

    def test_go_to_uses_ghls_keys_and_the_specs_target(self):
        goto = _by_name(self.wf, "Yes Branch Go To Step 27")
        theirs = [n for n in EXPORT_ALL["nodes"] if n["type"] == "goto"][0]
        self.assertEqual(set(_strip_annotations(goto["attributes"])), {"targetNodeId", "type"})
        self.assertEqual(set(_strip_annotations(theirs["attributes"])), {"targetNodeId", "type"})
        self.assertEqual(goto["attributes"]["type"], "goto")
        # GHL's default target (step 01) was never changed by hand, so whether a Go To may
        # jump into the other branch is unverified: keep the spec's target and warn.
        self.assertEqual(theirs["attributes"]["targetNodeId"], EXPORT_ALL["nodes"][0]["id"])
        self.assertEqual(goto["attributes"]["targetNodeId"], _by_name(self.wf, "No Branch Send SMS Last Step")["id"])
        self.assertEqual(len([w for w in self.warned if w.startswith("Go To ")]), 1)

    def test_triggers(self):
        self.assertEqual([t["name"] for t in self.wf["triggers"]], [t["name"] for t in EXPORT_ALL["triggers"]])
        for ours, theirs in zip(self.wf["triggers"], EXPORT_ALL["triggers"]):
            with self.subTest(trigger=ours["name"]):
                self.assertEqual(ours["type"], theirs["type"])
                self.assertEqual(ours["conditions"], theirs["conditions"])
                self.assertEqual(set(theirs) - set(ours), _TRIGGER_EXPORT_ONLY)
                self.assertEqual(set(ours) - set(theirs), set())
                self.assertEqual(_shape(ours["actions"]), _shape(theirs["actions"]))
                self.assertEqual(ours["actions"][0]["type"], theirs["actions"][0]["type"])
                for k in ("masterType", "belongs_to", "status", "deleted", "active", "name"):
                    self.assertEqual(ours[k], theirs[k], k)

    def test_annotation_port_matches_the_importer_on_known_keys(self):
        a = {"pipelineId": "p", "pipelineName": "P", "value": "v", "valueName": "V",
             "pipeline_id": "p", "pipeline_name": "P", "targetNodeId": "n", "targetNodeName": "N",
             "location_id": "l", "location_name": "L", "field": "f", "fieldName": "F",
             "user_list": ["u"], "user_listNames": ["U"], "campaignName": "kept", "name": "kept too"}
        self.assertEqual(_strip_annotations(a), {"pipelineId": "p", "value": "v", "pipeline_id": "p",
                                                 "targetNodeId": "n", "location_id": "l", "field": "f",
                                                 "user_list": ["u"], "campaignName": "kept",
                                                 "name": "kept too"})


def _one_step(step, ids=None):
    """Compile trigger -> step; (the step's record, unresolved, warnings)."""
    spec = _mini([_tag_trigger("t", "x"), dict(step, key="s")], [{"from": "t", "to": "s"}])
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", GHLCompileWarning)
        wf, unresolved = compile_ghl(spec, IDS if ids is None else ids, LOC)
    return wf["nodes"][0], unresolved, [str(w.message) for w in caught
                                        if issubclass(w.category, GHLCompileWarning)]


class TestExportVerifiedSteps(unittest.TestCase):
    """The steps the 2026-09-23 export changed, beyond the reference spec."""

    def _step(self, op, params, label="Step"):
        return {"kind": "app.action", "app": "ghl", "op": op, "label": label, "params": params}

    def test_ai_step_defaults_and_overrides(self):
        rec, _u, _w = _one_step(self._step("ai_step", {"prompt": "Summarise it"}))
        self.assertEqual((rec["type"], rec["attributes"]["type"]), ("chatgpt", "chatgpt"))
        a = rec["attributes"]
        self.assertEqual((a["promptText"], a["model"], a["temperature"], a["event"], a["actionType"]),
                         ("Summarise it", "gpt-5-mini", "0.2", "simple-prompt", "custom"))
        self.assertNotIn("prompt", a)
        self.assertEqual(rec["stepIndex"], 1)
        rec, _u, _w = _one_step(self._step("ai_step", {"prompt": "p", "model": "gpt-5", "temperature": 0.7}))
        self.assertEqual((rec["attributes"]["model"], rec["attributes"]["temperature"]), ("gpt-5", "0.7"))

    def test_review_request(self):
        rec, _u, _w = _one_step(self._step("send_review_request", {}))
        self.assertEqual(rec["type"], "review_request")
        self.assertEqual(rec["attributes"], {"type": "review_request", "overrideReviewLink": "default",
                                             "review_type": "sms"})

    def test_task_due_date_and_assignee(self):
        rec, _u, warned = _one_step(self._step("create_task", {"title": "Call", "due_in_days": 3}))
        a = rec["attributes"]
        self.assertEqual(a["dueDate"], {"duration": 3, "unit": "days", "skipWeekends": False})
        self.assertEqual(a["assignedTo"], "contact.assigned_user")
        self.assertEqual((rec["workflowsActionType"], rec["stepIndex"]), ("INTERNAL", 1))
        self.assertEqual(warned, [])

    def test_task_named_user_comes_from_the_id_map_or_stays_unset(self):
        step = self._step("create_task", {"title": "Call", "assign_to": "Dana"})
        rec, _u, warned = _one_step(step)
        self.assertNotIn("assignedTo", rec["attributes"])
        self.assertEqual(len(warned), 1)
        self.assertIn("user:Dana", warned[0])
        rec, _u, warned = _one_step(step, dict(IDS, **{"user:Dana": "uid-dana"}))
        self.assertEqual(rec["attributes"]["assignedTo"], "uid-dana")
        self.assertEqual(warned, [])

    def test_task_explicit_assigned_user_phrasings(self):
        for text in ("assigned user", "Contact owner", "the contact owner", "contact's owner",
                     "the contact's assigned user", "The Contact’s Assigned User."):
            with self.subTest(assign_to=text):
                rec, _u, warned = _one_step(self._step("create_task", {"title": "Call", "assign_to": text}))
                self.assertEqual(rec["attributes"]["assignedTo"], "contact.assigned_user")
                self.assertEqual(warned, [])

    def test_task_other_owner_or_role_goes_through_the_user_lookup(self):
        for text in ("the business owner", "owner", "assigned rep", "Sales Rep"):
            with self.subTest(assign_to=text):
                step = self._step("create_task", {"title": "Call", "assign_to": text})
                rec, _u, warned = _one_step(step)
                self.assertNotIn("assignedTo", rec["attributes"])
                self.assertEqual(len(warned), 1)
                self.assertIn("user:{}".format(text), warned[0])
                rec, _u, warned = _one_step(step, dict(IDS, **{"user:{}".format(text): "uid-x"}))
                self.assertEqual(rec["attributes"]["assignedTo"], "uid-x")
                self.assertEqual(warned, [])

    def test_update_contact_field_uses_the_field_id(self):
        rec, unresolved, _w = _one_step(self._step("update_contact_field", {"field": "Call Notes", "value": "v"}))
        self.assertEqual(rec["attributes"], {
            "type": "update_contact_field", "actionType": "update_field_data",
            "fields": [{"field": IDS["field:Call Notes"], "value": "v", "title": "Call Notes",
                        "type": "string", "date": ""}]})
        self.assertEqual(unresolved, [])
        rec, unresolved, _w = _one_step(self._step("update_contact_field", {"field": "Nope", "value": "v"}))
        self.assertEqual(unresolved, ["field:Nope"])

    def test_assign_user_ids_only_from_the_id_map(self):
        rec, _u, warned = _one_step(self._step("assign_user", {}))
        self.assertEqual(rec["attributes"]["user_list"], [])
        self.assertEqual((rec["attributes"]["traffic_weightage"], rec["attributes"]["traffic_index"],
                          rec["attributes"]["total_index"]), ({}, [], 0))
        self.assertEqual(len(warned), 1)
        ids = dict(IDS, **{"user:A": "ua", "user:B": "ub"})
        rec, _u, warned = _one_step(self._step("assign_user", {"user": ["A", "B", "C"]}), ids)
        a = rec["attributes"]
        self.assertEqual(a["user_list"], ["ua", "ub"])
        self.assertEqual(a["traffic_index"], [{"id": "ua", "indexes": [1]}, {"id": "ub", "indexes": [2]}])
        self.assertEqual(len(warned), 1)
        self.assertIn("C", warned[0])

    def test_no_location_ids_in_the_compiler(self):
        """No id from either real export (location, company, pipeline, stage, field,
        user, workflow, trigger and node ids) and none from the id map is written
        into the compiler. The location id is allowed only on main()'s default
        lines (the env default and its docstring mention)."""
        import re
        src = open(os.path.join(ROOT, "upwork_gen", "compile_ghl.py"), encoding="utf-8").read()
        id_like = re.compile(r"[A-Za-z0-9]{20}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
                             r"|[0-9a-f]{24}")
        found = {}

        def walk(obj, key, where):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    walk(v, k, where)
            elif isinstance(obj, list):
                for v in obj:
                    walk(v, key, where)
            elif isinstance(obj, str) and id_like.fullmatch(obj):
                found.setdefault(obj, set()).add("{} {}".format(where, key))
        walk(EXPORT_ALL, None, "ghl_export_reference_all_types.json")
        walk(EXPORT, None, "ghl_export_sales_request_follow_up.json")
        for kind in ("locationId", "companyId", "pipeline_id", "pipeline_stage_id", "field",
                     "user_list", "workflow_id", "id"):
            self.assertTrue(any(w.endswith(" " + kind) for ws in found.values() for w in ws), kind)
        self.assertIn(LOC, found)
        self.assertIn(EXPORT["triggers"][0]["id"], found)
        for key, value in IDS.items():
            if not key.startswith("_") and isinstance(value, str):
                found.setdefault(value, set()).add("id map " + key)

        lines = src.splitlines()
        start = next(i for i, l in enumerate(lines) if l.startswith("def main("))
        end = next((i for i in range(start + 1, len(lines)) if lines[i] and not lines[i][0].isspace()
                    and not lines[i].startswith(")")), len(lines))
        for value, where in sorted(found.items()):
            hits = [i for i, l in enumerate(lines) if value in l]
            if value == LOC:
                for i in hits:
                    default_line = ('os.environ.get("UPWORK_GHL_LOCATION", "{}")'.format(LOC) in lines[i]
                                    or "(default {})".format(LOC) in lines[i])
                    self.assertTrue(start <= i < end and default_line,
                                    "location id on compile_ghl.py:{}".format(i + 1))
                self.assertTrue(hits)
            else:
                self.assertEqual(hits, [], "{} ({}) in compile_ghl.py".format(value, sorted(where)))


class TestGoToAcrossBranches(unittest.TestCase):
    def _gate(self):
        return {"key": "c", "kind": "flow.branch", "label": "Has x", "params": {"condition": "tag \"x\""}}

    def _goto(self, key, target):
        return {"key": key, "kind": "app.action", "app": "ghl", "op": "go_to", "label": "Jump " + key,
                "params": {"target": target}}

    def _compile(self, nodes, edges):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", GHLCompileWarning)
            wf, _u = compile_ghl(_mini(nodes, edges), IDS, LOC)
        return wf, [str(w.message) for w in caught if issubclass(w.category, GHLCompileWarning)]

    def test_go_to_into_the_sibling_branch_warns_and_keeps_the_target(self):
        wf, warned = self._compile(
            [_tag_trigger("t", "x"), self._gate(), self._goto("g", "Text b"), _sms("b")],
            [{"from": "t", "to": "c"}, {"from": "c", "to": "g", "branch": "true"},
             {"from": "c", "to": "b", "branch": "false"}])
        self.assertEqual(_by_name(wf, "Jump g")["attributes"]["targetNodeId"], _by_name(wf, "Text b")["id"])
        self.assertEqual(len(warned), 1)
        self.assertIn('"Jump g" points at "Text b"', warned[0])
        self.assertIn("GHL may not allow", warned[0])

    def test_go_to_back_to_the_main_line_or_within_its_branch_does_not_warn(self):
        _wf, warned = self._compile(
            [_tag_trigger("t", "x"), _sms("a"), self._gate(), _sms("b"), self._goto("g", "Text b"),
             self._goto("h", "Text a")],
            [{"from": "t", "to": "a"}, {"from": "a", "to": "c"}, {"from": "c", "to": "b", "branch": "true"},
             {"from": "b", "to": "g"}, {"from": "c", "to": "h", "branch": "false"}])
        self.assertEqual(warned, [])

    def test_main_prints_the_warning(self):
        import contextlib
        import io
        err = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stderr(err), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(compile_ghl_main([REFERENCE_SPEC, os.path.join(tmp, "r.ghl.json")]), 0)
        self.assertIn("check after import: Go To \"Yes Branch Go To Step 27\"", err.getvalue())


class TestStructure(unittest.TestCase, GraphChecks):
    def test_branching_non_branch_node_raises(self):
        spec = _mini([_tag_trigger("t", "x"), _sms("a"), _sms("b"), _sms("c")],
                     [{"from": "t", "to": "a"}, {"from": "a", "to": "b"}, {"from": "a", "to": "c"}])
        with self.assertRaises(SpecError) as ctx:
            compile_ghl(spec, IDS, LOC)
        self.assertIn("flow.branch", str(ctx.exception))

    def test_unlabelled_if_else_edge_raises(self):
        spec = _mini([_tag_trigger("t", "x"),
                      {"key": "c", "kind": "flow.branch", "label": "Check", "params": {"condition": "tag \"x\""}},
                      _sms("a")],
                     [{"from": "t", "to": "c"}, {"from": "c", "to": "a"}])
        with self.assertRaises(SpecError):
            compile_ghl(spec, IDS, LOC)

    def test_end_terminates_chain(self):
        spec = _mini([_tag_trigger("t", "x"), _sms("a"),
                      {"key": "e", "kind": "app.action", "app": "ghl", "op": "end", "label": "Stop", "params": {}}],
                     [{"from": "t", "to": "a"}, {"from": "a", "to": "e"}])
        wf, _ = compile_ghl(spec, IDS, LOC)
        self.assertEqual([n["name"] for n in wf["nodes"]], ["Text a"])
        self.assertEqual(wf["nodes"][0]["next"], "")
        self.assert_graph_ok(wf)

    def test_end_in_a_branch_and_noop_kind(self):
        spec = _mini([_tag_trigger("t", "x"),
                      {"key": "c", "kind": "flow.branch", "label": "Has x",
                       "params": {"condition": "contact does not have tag \"x\""}},
                      _sms("a"), {"key": "e", "kind": "flow.noop", "label": "End"}],
                     [{"from": "t", "to": "c"}, {"from": "c", "to": "a", "branch": "true"},
                      {"from": "c", "to": "e", "branch": "false"}])
        wf, unresolved = compile_ghl(spec, IDS, LOC)
        self.assert_graph_ok(wf)
        none = [n for n in wf["nodes"] if n.get("nodeType") == "branch-no"][0]
        self.assertNotIn("next", none)
        cond = [n for n in wf["nodes"] if n.get("nodeType") == "condition-node"][0]
        c = cond["attributes"]["branches"][0]["segments"][0]["conditions"][0]
        self.assertEqual(c["conditionOperator"], "index-of-false")
        self.assertEqual(unresolved, [])

    def test_node_after_end_raises(self):
        spec = _mini([_tag_trigger("t", "x"),
                      {"key": "e", "kind": "flow.noop", "label": "End"}, _sms("a")],
                     [{"from": "t", "to": "e"}, {"from": "e", "to": "a"}])
        with self.assertRaises(SpecError):
            compile_ghl(spec, IDS, LOC)

    def test_plain_english_condition_keeps_skeleton_and_is_reported(self):
        spec = _mini([_tag_trigger("t", "x"),
                      {"key": "c", "kind": "flow.branch", "label": "Big Job",
                       "params": {"condition": "opportunity value is over 5000"}},
                      _sms("a")],
                     [{"from": "t", "to": "c"}, {"from": "c", "to": "a", "branch": "true"}])
        wf, unresolved = compile_ghl(spec, IDS, LOC)
        self.assert_graph_ok(wf)
        cond = [n for n in wf["nodes"] if n.get("nodeType") == "condition-node"][0]
        self.assertEqual(cond["attributes"]["branches"][0]["segments"], [{"operator": "and", "conditions": []}])
        self.assertEqual(unresolved, ["condition:Big Job -> opportunity value is over 5000"])

    def test_names_that_are_not_strings_are_a_spec_error(self):
        """A pipeline, stage or If/Else tag that is a dict or a number is refused
        with a clear SpecError, never an AttributeError or an object named after
        its repr (ghl_prereqs refuses the same specs)."""
        opp = {"key": "o", "kind": "app.action", "app": "ghl", "op": "create_opportunity", "label": "Opp",
               "params": {"pipeline": {"name": "Demo", "stages": ["New", "Won"]}, "stage": "New"}}
        upd = {"key": "o", "kind": "app.action", "app": "ghl", "op": "update_opportunity", "label": "Opp",
               "params": {"pipeline": "Demo", "stage": {"name": "Won"}}}
        branch = {"key": "o", "kind": "flow.branch", "label": "Opp",
                  "params": {"tag": {"name": "vip"}, "condition": "has vip"}}
        # Max-2 review, defect 2: the rest of the params ghl_prereqs names an
        # object after (a dict `field` used to compile, and to be created).
        field = {"key": "o", "kind": "app.action", "app": "ghl", "op": "update_contact_field", "label": "Opp",
                 "params": {"field": {"name": "Lead Score"}, "value": "1"}}
        output = {"key": "o", "kind": "ai.llm", "label": "Opp",
                  "params": {"prompt": "x", "output_field": ["Summary"]}}
        add_tag = {"key": "o", "kind": "app.action", "app": "ghl", "op": "add_tag", "label": "Opp",
                   "params": {"tag": 5}}
        stages = {"key": "o", "kind": "app.action", "app": "ghl", "op": "create_opportunity", "label": "Opp",
                  "params": {"pipeline": "Demo", "stage": "New", "stages": [{"name": "New"}]}}
        for node, message in ((opp, "`pipeline` must be a pipeline name (a string)"),
                              (upd, "`stage` must be a stage name (a string)"),
                              (branch, "`tag` must be a tag name or a list of tag names"),
                              (field, "`field` must be a custom field name (a string), got {'name': 'Lead Score'}"),
                              (output, "`output_field` must be a custom field name (a string), got ['Summary']"),
                              (add_tag, "`tag` must be one tag name (a string), got 5: one tag per step; use two steps"),
                              (stages, "every entry in `stages` must be a stage name, got {'name': 'New'}")):
            with self.assertRaises(SpecError) as ctx:
                compile_ghl(_mini([_tag_trigger("t", "x"), node], [{"from": "t", "to": "o"}]), IDS, LOC)
            self.assertIn("node 'o' (Opp): " + message, str(ctx.exception))

    def test_value_after_a_tag_list_named_only_by_a_later_noun_is_unresolved(self):
        """Max-2 review, defect 1: a subject noun after a value does not make it
        another subject's once a tag list is found, so these are no longer
        compiled to the inverse tag test (or a tag test minus the stage)."""
        for cond in ('Contact has tag "hot-lead" and is not in the "Closed" stage',
                     'has tag "a" and has no "Lost" status',
                     'Contact has tag "hot-lead" and is in the "Won" stage'):
            spec = _mini([_tag_trigger("t", "x"),
                          {"key": "c", "kind": "flow.branch", "label": "Check", "params": {"condition": cond}},
                          _sms("a")],
                         [{"from": "t", "to": "c"}, {"from": "c", "to": "a", "branch": "true"}])
            wf, unresolved = compile_ghl(spec, IDS, LOC)
            node = [n for n in wf["nodes"] if n.get("nodeType") == "condition-node"][0]
            self.assertEqual(node["attributes"]["branches"][0]["segments"][0]["conditions"], [], cond)
            self.assertEqual(unresolved, ["condition:Check -> " + cond], cond)

    def test_uncertain_tag_condition_is_unresolved_not_a_reply_check(self):
        def branch(cond):
            spec = _mini([_tag_trigger("t", "x"),
                          {"key": "c", "kind": "flow.branch", "label": "Check", "params": {"condition": cond}},
                          _sms("a")],
                         [{"from": "t", "to": "c"}, {"from": "c", "to": "a", "branch": "true"}])
            wf, unresolved = compile_ghl(spec, IDS, LOC)
            node = [n for n in wf["nodes"] if n.get("nodeType") == "condition-node"][0]
            return node["attributes"]["branches"][0]["segments"][0]["conditions"], unresolved

        conditions, unresolved = branch('has tag "replied" or is "x"')
        self.assertEqual(conditions, [])
        self.assertEqual(unresolved, ['condition:Check -> has tag "replied" or is "x"'])
        conditions, unresolved = branch("contact replied")  # names no tags: the verified reply check
        self.assertEqual([(c["conditionSubType"], c["conditionValue"]) for c in conditions],
                         [("contact_replied", "true")])
        self.assertEqual(unresolved, [])

    def test_converging_branches_copy_the_tail(self):
        spec = _mini([_tag_trigger("t", "x"),
                      {"key": "c", "kind": "flow.branch", "label": "Has x", "params": {"condition": "tag \"x\""}},
                      _sms("a"), _sms("b"), _sms("z")],
                     [{"from": "t", "to": "c"}, {"from": "c", "to": "a", "branch": "true"},
                      {"from": "c", "to": "b", "branch": "false"}, {"from": "a", "to": "z"}, {"from": "b", "to": "z"}])
        wf, _ = compile_ghl(spec, IDS, LOC)
        self.assert_graph_ok(wf)
        self.assertEqual(len([n for n in wf["nodes"] if n["name"] == "Text z"]), 2)

    def test_wait_units(self):
        for unit, want in (("hours", "hour"), ("hour", "hour"), ("minutes", "minutes"), ("days", "days")):
            spec = _mini([_tag_trigger("t", "x"),
                          {"key": "w", "kind": "flow.wait", "label": "Wait", "params": {"amount": 2, "unit": unit}}],
                         [{"from": "t", "to": "w"}])
            wf, _ = compile_ghl(spec, IDS, LOC)
            self.assertEqual(wf["nodes"][0]["attributes"]["startAfter"], {"when": "after", "type": want, "value": 2})
        spec = _mini([_tag_trigger("t", "x"),
                      {"key": "w", "kind": "flow.wait", "label": "Wait 2 Weeks", "params": {"amount": 2, "unit": "weeks"}}],
                     [{"from": "t", "to": "w"}])
        wf, _ = compile_ghl(spec, IDS, LOC)
        self.assertEqual(wf["nodes"][0]["attributes"]["startAfter"]["value"], 14)

    def test_form_trigger_filter_only_when_resolved(self):
        form = {"key": "t", "kind": "trigger.app", "app": "ghl", "op": "form_submitted", "label": "Form",
                "params": {"form": "Intake"}}
        spec = _mini([form, _sms("a")], [{"from": "t", "to": "a"}])
        wf, unresolved = compile_ghl(spec, IDS, LOC)
        self.assertEqual(wf["triggers"][0]["conditions"], [])
        self.assertEqual(unresolved, ["form:Intake"])
        ids = dict(IDS); ids["form:Intake"] = "FORMID123"
        wf, unresolved = compile_ghl(spec, ids, LOC)
        self.assertEqual(wf["triggers"][0]["conditions"][0]["value"], "FORMID123")
        self.assertEqual(unresolved, [])

    def test_internal_email_to_address_uses_custom_email(self):
        n = {"key": "n", "kind": "app.action", "app": "ghl", "op": "internal_notification", "label": "Mail me",
             "params": {"type": "email", "to": "owner@example.com", "subject": "S", "message": "M"}}
        wf, _ = compile_ghl(_mini([_tag_trigger("t", "x"), n], [{"from": "t", "to": "n"}]), IDS, LOC)
        em = wf["nodes"][0]["attributes"]["email"]
        self.assertEqual((em["userType"], em["to"], em["html"]), ("custom_email", "owner@example.com", "M"))


class TestLoopsAndTriggers(unittest.TestCase, GraphChecks):
    def test_loop_edge_becomes_go_to(self):
        spec = _mini([_tag_trigger("t", "x"), _sms("a"), _sms("b")],
                     [{"from": "t", "to": "a"}, {"from": "a", "to": "b"},
                      {"from": "b", "to": "a", "loop": True}])
        wf, unresolved = compile_ghl(spec, IDS, LOC)
        self.assert_graph_ok(wf)
        self.assertEqual(unresolved, [])
        self.assertEqual([n["name"] for n in wf["nodes"]], ["Text a", "Text b", "Go To Text a"])
        a, b, goto = wf["nodes"]
        self.assertEqual(goto["type"], "goto")
        self.assertEqual(goto["attributes"], {"targetNodeId": a["id"], "type": "goto", "targetNodeName": "Text a"})
        self.assertEqual((b["next"], b["nextName"]), (goto["id"], "Go To Text a"))
        self.assertEqual((goto["parentKey"], goto["next"], goto["order"]), (b["id"], "", 2))
        self.assertEqual(wf["references"]["other"][goto["id"]], "Go To Text a")

    def test_loop_edge_in_an_if_else_branch(self):
        spec = _mini([_tag_trigger("t", "x"), _sms("a"),
                      {"key": "c", "kind": "flow.branch", "label": "Has x", "params": {"condition": "tag \"x\""}},
                      _sms("b")],
                     [{"from": "t", "to": "a"}, {"from": "a", "to": "c"},
                      {"from": "c", "to": "b", "branch": "true"},
                      {"from": "c", "to": "a", "branch": "false", "loop": True}])
        wf, _ = compile_ghl(spec, IDS, LOC)
        self.assert_graph_ok(wf)
        none = [n for n in wf["nodes"] if n.get("nodeType") == "branch-no"][0]
        goto = [n for n in wf["nodes"] if n["type"] == "goto"][0]
        self.assertEqual(none["next"], goto["id"])
        self.assertEqual(goto["parent"], none["id"])
        self.assertEqual(goto["attributes"]["targetNodeId"], _by_name(wf, "Text a")["id"])

    def test_loop_edge_that_cannot_be_a_go_to_raises(self):
        cases = [
            # loop plus a normal next step: a Go To would have to sit mid-chain
            ([_tag_trigger("t", "x"), _sms("a"), _sms("b"), _sms("c")],
             [{"from": "t", "to": "a"}, {"from": "a", "to": "b"}, {"from": "b", "to": "c"},
              {"from": "b", "to": "a", "loop": True}]),
            # two loops out of one step
            ([_tag_trigger("t", "x"), _sms("a"), _sms("b")],
             [{"from": "t", "to": "a"}, {"from": "a", "to": "b"},
              {"from": "b", "to": "a", "loop": True}, {"from": "b", "to": "b", "loop": True}]),
            # loop back to the trigger
            ([_tag_trigger("t", "x"), _sms("a")],
             [{"from": "t", "to": "a"}, {"from": "a", "to": "t", "loop": True}]),
        ]
        for nodes, edges in cases:
            with self.assertRaises(SpecError):
                compile_ghl(_mini(nodes, edges), IDS, LOC)

    def test_trigger_without_next_step_names_it(self):
        lonely = _mini([_tag_trigger("t1", "a", "1 - Tag a Added"), _sms("x"),
                        _tag_trigger("t2", "b", "2 - Tag b Added")],
                       [{"from": "t1", "to": "x"}])
        for fn in (compile_ghl, compile_ghl_many):
            with self.assertRaises(SpecError) as ctx:
                fn(lonely, IDS, LOC)
            self.assertIn("trigger Tag b Added ('t2') has no next step", str(ctx.exception))
        alone = _mini([_tag_trigger("t", "a", "Only Trigger"), _sms("x")], [])
        with self.assertRaises(SpecError) as ctx:
            compile_ghl(alone, IDS, LOC)
        self.assertIn("trigger Only Trigger ('t') has no next step", str(ctx.exception))


class TestGenerateNote(unittest.TestCase):
    def test_build_note_lists_the_ghl_files(self):
        from upwork_gen.generate import build
        res = build(_load(REFERENCE_SPEC), "gohighlevel", "compiler")
        note = [w for w in res.warnings if w.startswith("gohighlevel:")]
        self.assertEqual(len(note), 1)
        for part in ("import JSON", ".ghl.json", ".ghl-prompt.txt", ".ghl-prereqs.txt"):
            self.assertIn(part, note[0])
        self.assertFalse([w for w in res.warnings if "no importable workflow format" in w])


class TestMultiWorkflow(unittest.TestCase, GraphChecks):
    def _two_chains(self):
        return _mini([_tag_trigger("t1", "a", "1 - Tag a Added"), _sms("x"),
                      _tag_trigger("t2", "b", "2 - Tag b Added"), _sms("y"), _sms("z")],
                     [{"from": "t1", "to": "x"}, {"from": "t2", "to": "y"}, {"from": "y", "to": "z"}],
                     title="Two Chains")

    def test_separate_chains_make_separate_workflows(self):
        parts = compile_ghl_many(self._two_chains(), IDS, LOC)
        self.assertEqual([p[0] for p in parts], ["Tag a Added", "Tag b Added"])
        self.assertEqual([len(p[1]["nodes"]) for p in parts], [1, 2])
        self.assertEqual(parts[0][1]["workflowName"], "Two Chains - Tag a Added")
        self.assertNotEqual(parts[0][1]["workflowId"], parts[1][1]["workflowId"])
        for _s, wf, _u in parts:
            self.assert_graph_ok(wf)
            self.assertEqual(len(wf["triggers"]), 1)

    def test_compile_ghl_refuses_a_multi_workflow_spec(self):
        with self.assertRaises(SpecError):
            compile_ghl(self._two_chains(), IDS, LOC)

    def test_shared_downstream_stays_one_workflow(self):
        spec = _mini([_tag_trigger("t1", "a"), _tag_trigger("t2", "b"), _sms("x")],
                     [{"from": "t1", "to": "x"}, {"from": "t2", "to": "x"}])
        parts = compile_ghl_many(spec, IDS, LOC)
        self.assertEqual(len(parts), 1)
        self.assertEqual(parts[0][0], "")
        self.assertEqual(len(parts[0][1]["triggers"]), 2)
        wf, _ = compile_ghl(spec, IDS, LOC)
        self.assertEqual(len(wf["triggers"]), 2)

    def test_single_trigger_many_matches_compile_ghl(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", GHLCompileWarning)  # the reference spec warns on purpose
            parts = compile_ghl_many(_load(REFERENCE_SPEC), IDS, LOC)
        self.assertEqual(len(parts), 1)
        self.assertEqual(len(split_ghl_spec(_load(REFERENCE_SPEC))), 1)

    def test_write_output_names_one_file_per_workflow(self):
        from upwork_gen.generate import Result, write_output
        spec = self._two_chains()
        with tempfile.TemporaryDirectory() as tmp:
            res = write_output(Result(spec=spec, workflow={}, platform="gohighlevel", engine="compiler"),
                               out_dir=tmp, copy=False)
            names = sorted(f for f in os.listdir(tmp) if f.endswith(".ghl.json"))
            self.assertEqual(names, ["two-chains--1-tag-a-added.ghl.json", "two-chains--2-tag-b-added.ghl.json"])
            self.assertEqual(os.path.basename(res.ghl_json_path), names[0])
            self.assertEqual([os.path.basename(p) for p in res.ghl_json_paths], names)

    def test_write_output_keeps_check_warnings_for_every_spec(self):
        """Python shows a given warning once per process; the result must carry the
        "check after import" lines for the second compile of a batch too."""
        from upwork_gen.generate import Result, write_output
        results = []
        with tempfile.TemporaryDirectory() as tmp, warnings.catch_warnings():
            # Even with the warnings module showing nothing, the result carries them.
            warnings.simplefilter("ignore", GHLCompileWarning)
            for _ in range(2):
                spec = _load(REFERENCE_SPEC)
                results.append(write_output(Result(spec=spec, workflow={}, platform="gohighlevel",
                                                   engine="compiler"), out_dir=tmp, copy=False))
        checks = [[w for w in r.warnings if w.startswith("ghl: check after import: ")] for r in results]
        self.assertEqual(len(checks[0]), 2)  # Go To into the other branch, Assign to user with no user
        self.assertEqual(checks[0], checks[1])
        self.assertTrue(any("Go To " in w for w in checks[1]))
        self.assertTrue(any("assign to user" in w for w in checks[1]))

    def test_write_output_does_not_also_raise_ghl_warnings(self):
        """The checks go to the notes only. Raised as well, the first spec of a
        process showed each one twice (stderr and notes); with the filter at
        "always" none may escape write_output, and the notes keep both."""
        from upwork_gen.generate import Result, write_output
        with tempfile.TemporaryDirectory() as tmp, warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            res = write_output(Result(spec=_load(REFERENCE_SPEC), workflow={}, platform="gohighlevel",
                                      engine="compiler"), out_dir=tmp, copy=False)
        escaped = [str(w.message) for w in caught if issubclass(w.category, GHLCompileWarning)]
        self.assertEqual(escaped, [])
        checks = [w for w in res.warnings if w.startswith("ghl: check after import: ")]
        self.assertEqual(len(checks), 2)
        self.assertTrue(any("Go To " in w for w in checks))
        self.assertTrue(any("assign to user" in w for w in checks))

    def test_write_output_passes_other_warnings_on(self):
        """Only GHLCompileWarning is swallowed; any other warning raised during
        the compile still reaches the caller, unchanged."""
        from unittest import mock

        from upwork_gen.compile_ghl import GHLCompiler
        from upwork_gen.generate import Result, write_output
        real_compile = GHLCompiler.compile

        def compile_and_warn(self):
            warnings.warn("unrelated deprecation", DeprecationWarning)
            return real_compile(self)

        with tempfile.TemporaryDirectory() as tmp, warnings.catch_warnings(record=True) as caught, \
                mock.patch.object(GHLCompiler, "compile", compile_and_warn):
            warnings.simplefilter("always")
            write_output(Result(spec=_load(REFERENCE_SPEC), workflow={}, platform="gohighlevel",
                                engine="compiler"), out_dir=tmp, copy=False)
        other = [(w.category, str(w.message)) for w in caught if not issubclass(w.category, GHLCompileWarning)]
        self.assertIn((DeprecationWarning, "unrelated deprecation"), other)
        self.assertFalse(any(issubclass(w.category, GHLCompileWarning) for w in caught))

    def test_batch_prints_each_check_once_per_spec(self):
        """Two jobs with the reference spec through `batch`, in a fresh process
        (the warnings module's once-per-process memory is empty, as in real
        use): each check appears exactly once per spec across stdout and stderr."""
        import subprocess
        with tempfile.TemporaryDirectory() as tmp:
            jobs = []
            for name in ("job-a", "job-b"):
                job = os.path.join(tmp, "jobs", name)
                os.makedirs(job)
                with open(REFERENCE_SPEC, encoding="utf-8") as src, \
                        open(os.path.join(job, "spec.json"), "w", encoding="utf-8") as dst:
                    dst.write(src.read())
                jobs.append(job)
            out_dir = os.path.join(tmp, "out")
            os.makedirs(out_dir)
            env = dict(os.environ)
            env.pop("PYTHONWARNINGS", None)
            proc = subprocess.run(
                [sys.executable, "-m", "upwork_gen", "batch"] + jobs
                + ["--no-learn", "--no-log", "--no-commit", "--out-dir", out_dir],
                cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                universal_newlines=True, timeout=300)
            # Both specs compiled into the temp dirs, nowhere else.
            for job in jobs:
                self.assertTrue(any(f.endswith(".ghl.json") for f in os.listdir(job)), proc.stdout)
        combined = proc.stdout + proc.stderr
        self.assertNotIn("GHLCompileWarning", combined)
        from upwork_gen.compile_ghl import GHLCompiler
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", GHLCompileWarning)
            c = GHLCompiler(_load(REFERENCE_SPEC), IDS, LOC)
            c.compile()
        self.assertEqual(len(c.warnings), 2)  # Go To into the other branch, Assign to user with no user
        sections = {s.split("\n", 1)[0]: s for s in proc.stdout.split("\n== ")[1:]}
        for message in c.warnings:
            self.assertEqual(combined.count(message), 2, message)  # job-a once, job-b once
            for name in ("job-a", "job-b"):
                self.assertEqual(sections[name].count("ghl: check after import: " + message), 1,
                                 (name, message))



class TestTagStepGaps(unittest.TestCase):
    """One tag per tag step, and a negative-sounding gate must set `negate`."""

    def _tag_step(self, op, tag):
        params = {"tag": tag} if op != "goal" else {"goal_type": "tag_added", "tag": tag}
        node = {"key": "s", "kind": "app.action", "app": "ghl", "op": op, "label": "Step s", "params": params}
        return _mini([_tag_trigger("t", "x"), node], [{"from": "t", "to": "s"}])

    def _gate(self, params):
        spec = _mini([_tag_trigger("t", "x"),
                      {"key": "c", "kind": "flow.branch", "label": "Check", "params": params},
                      _sms("a")],
                     [{"from": "t", "to": "c"}, {"from": "c", "to": "a", "branch": "true"}])
        wf, _ = compile_ghl(spec, IDS, LOC)
        node = [n for n in wf["nodes"] if n.get("nodeType") == "condition-node"][0]
        return node["attributes"]["branches"][0]["segments"][0]["conditions"]

    def test_tag_step_with_a_list_is_an_error_naming_the_step(self):
        for op in ("add_tag", "remove_tag", "goal"):
            for tag in (["bid-replied", "hot"], ["bid-replied"], {"name": "hot"}, 3):
                with self.assertRaises(SpecError, msg="{} {!r}".format(op, tag)) as cm:
                    compile_ghl(self._tag_step(op, tag), IDS, LOC)
                self.assertIn("'s'", str(cm.exception))
                self.assertIn("Step s", str(cm.exception))
                self.assertIn("one tag per step; use two steps", str(cm.exception))

    def test_tag_step_with_one_string_still_compiles(self):
        for op in ("add_tag", "remove_tag", "goal"):
            wf, _ = compile_ghl(self._tag_step(op, "bid-replied"), IDS, LOC)
            self.assertNotIn("[['bid-replied']]", repr(wf["nodes"]), op)

    def test_gate_tag_may_still_be_a_list(self):
        conditions = self._gate({"condition": 'Contact has tag "a" or "b"', "tag": ["a", "b"]})
        self.assertEqual([(c["conditionOperator"], c["conditionValue"]) for c in conditions],
                         [("index-of-true", ["a", "b"])])

    def test_negative_gate_without_negate_is_an_error(self):
        for cond in ('Contact does not have tag "bid-sent"', "Contact doesn't have tag \"bid-sent\"",
                     'Contact without tag "bid-sent"', 'Tags exclude "bid-sent"', 'Contact lacks tag "bid-sent"',
                     'Contact is not tagged "bid-sent"', 'Does not have "bid-sent"',
                     'Contact has no tag "bid-sent"', 'Contact is missing tag "bid-sent"',
                     "Contact isn't tagged \"bid-sent\"", 'Contact not tagged "bid-sent"',
                     "Contacts don't have tag \"bid-sent\"", 'Contact has not been tagged "bid-sent"',
                     'Tag "bid-sent" not present', 'Tag != "bid-sent"', 'Tags do not include "bid-sent"',
                     "Contact hasn't got tag \"bid-sent\"", "Contacts haven't got tag \"bid-sent\"",
                     "Tags aren't \"bid-sent\"", "Contact won't have tag \"bid-sent\"",
                     'Contact doesn\u2019t have tag "bid-sent"',
                     'Contact was never tagged "bid-sent"', 'Never tagged "bid-sent"',
                     'Tag "bid-sent" is absent', 'Tag "bid-sent" was removed',
                     'Contact lacking tag "bid-sent"', 'Contact NEVER got tag "bid-sent"'):
            with self.assertRaises(SpecError, msg=cond) as cm:
                self._gate({"condition": cond, "tag": "bid-sent"})
            self.assertIn("'c'", str(cm.exception))
            self.assertIn('"negate": true', str(cm.exception))

    def test_negate_null_counts_as_unset(self):
        with self.assertRaises(SpecError) as cm:
            self._gate({"condition": 'Contact has no tag "bid-sent"', "tag": "bid-sent", "negate": None})
        self.assertIn('"negate": true', str(cm.exception))
        conditions = self._gate({"condition": 'Contact has tag "bid-sent"', "tag": "bid-sent", "negate": None})
        self.assertEqual([(c["conditionOperator"], c["conditionValue"]) for c in conditions],
                         [("index-of-true", ["bid-sent"])])

    def test_negative_words_inside_a_quoted_tag_name_do_not_trip_the_check(self):
        for tag in ("without-reply", "lacks-budget", "excludes-promo", "doesn't-answer",
                    "does not call", "not have card", "no-show", "not-interested", "missing-info"):
            for cond in ('Contact has tag "{}"'.format(tag), "Contact has tag '{}'".format(tag)):
                if "'" in tag and cond.endswith("'"):
                    continue  # a straight apostrophe cannot sit inside single quotes
                conditions = self._gate({"condition": cond, "tag": tag})
                self.assertEqual([(c["conditionOperator"], c["conditionValue"]) for c in conditions],
                                 [("index-of-true", [tag])], cond)

    def test_never_absent_removed_lacking_inside_a_quoted_tag_name_do_not_trip_the_check(self):
        for tag in ("never-replied", "absent", "removed-from-list", "lacking info", "Never Booked"):
            for cond in ('Contact has tag "{}"'.format(tag), "Tag includes '{}'".format(tag)):
                conditions = self._gate({"condition": cond, "tag": tag})
                self.assertEqual([(c["conditionOperator"], c["conditionValue"]) for c in conditions],
                                 [("index-of-true", [tag])], cond)

    def test_negative_sentence_around_a_negative_sounding_tag_still_errors(self):
        with self.assertRaises(SpecError):
            self._gate({"condition": 'Contact does not have tag "without-reply"', "tag": "without-reply"})
        conditions = self._gate({"condition": 'Contact does not have tag "without-reply"',
                                 "tag": "without-reply", "negate": True})
        self.assertEqual(conditions[0]["conditionOperator"], "index-of-false")

    def test_explicit_negate_wins_without_reading_the_sentence(self):
        cond = 'Contact does not have tag "bid-sent"'
        for negate, operator in ((True, "index-of-false"), (False, "index-of-true")):
            conditions = self._gate({"condition": cond, "tag": "bid-sent", "negate": negate})
            self.assertEqual([(c["conditionOperator"], c["conditionValue"]) for c in conditions],
                             [(operator, ["bid-sent"])])
        conditions = self._gate({"condition": 'Contact has tag "bid-sent"', "tag": "bid-sent", "negate": True})
        self.assertEqual(conditions[0]["conditionOperator"], "index-of-false")

    def test_positive_gate_without_negate_is_unchanged(self):
        conditions = self._gate({"condition": 'Contact has tag "bid-sent"', "tag": "bid-sent"})
        self.assertEqual([(c["conditionOperator"], c["conditionValue"]) for c in conditions],
                         [("index-of-true", ["bid-sent"])])

    def test_negative_gate_without_params_tag_still_reads_the_sentence(self):
        conditions = self._gate({"condition": 'Contact does not have tag "bid-sent"'})
        self.assertEqual([(c["conditionOperator"], c["conditionValue"]) for c in conditions],
                         [("index-of-false", ["bid-sent"])])

    def test_gates_without_params_tag_are_not_checked(self):
        for cond, operator in (('Contact has no tag "bid-sent"', "index-of-false"),
                               ('Tags do not include "bid-sent"', "index-of-false"),
                               ('Contact has tag "bid-sent"', "index-of-true")):
            conditions = self._gate({"condition": cond})
            self.assertEqual(conditions[0]["conditionOperator"], operator, cond)

    # -- gates without params.tag read the sentence outside its quoted spans --
    def _ops(self, conditions):
        return [(c["conditionOperator"], c["conditionValue"]) for c in conditions]

    def test_untagged_gate_ignores_negative_words_inside_quoted_tag_names(self):
        for tag in ("no-show", "not-interested", "missing-info", "without-reply"):
            for cond in ('Contact has tag "{}"'.format(tag), "Contact has tag '{}'".format(tag)):
                self.assertEqual(self._ops(self._gate({"condition": cond})), [("index-of-true", [tag])], cond)

    def test_untagged_gate_reads_negative_sentences_as_index_of_false(self):
        for cond in ("Contacts don't have tag \"x\"", "Contact hasn't got tag \"x\"",
                     'Contact never got tag "x"', 'Tag "x" was removed'):
            self.assertEqual(self._ops(self._gate({"condition": cond})), [("index-of-false", ["x"])], cond)

    def _reply(self, cond):
        spec = _mini([_tag_trigger("t", "x"),
                      {"key": "c", "kind": "flow.branch", "label": "Check", "params": {"condition": cond}},
                      _sms("a")],
                     [{"from": "t", "to": "c"}, {"from": "c", "to": "a", "branch": "true"}])
        wf, _ = compile_ghl(spec, IDS, LOC)
        node = [n for n in wf["nodes"] if n.get("nodeType") == "condition-node"][0]
        return [(c["conditionSubType"], c["conditionValue"])
                for c in node["attributes"]["branches"][0]["segments"][0]["conditions"]]

    def test_negative_reply_gates_compile_to_replied_false(self):
        for cond in ("Contact hasn't replied", "Contact didn't reply", "Contact never replied",
                     "Contact hasnt replied", "Contact didnt reply", "Contact has not replied"):
            self.assertEqual(self._reply(cond), [("contact_replied", "false")], cond)
        self.assertEqual(self._reply("Contact replied"), [("contact_replied", "true")])

    WIDENED = ("lack", "lacked", "untagged", "excluding", "excluded",
               "doesnt", "dont", "isnt", "hasnt", "havent", "didnt")

    def test_widened_negative_words_need_negate(self):
        sentences = {"lack": 'Contacts lack tag "bid-sent"', "lacked": 'Contact lacked tag "bid-sent"',
                     "untagged": 'Contact untagged from tag "bid-sent"', "excluding": 'Contacts excluding tag "bid-sent"',
                     "excluded": 'Tag "bid-sent" excluded', "doesnt": 'Contact doesnt have tag "bid-sent"',
                     "dont": 'Contacts dont have tag "bid-sent"', "isnt": 'Contact isnt carrying tag "bid-sent"',
                     "hasnt": 'Contact hasnt got tag "bid-sent"', "havent": 'Contacts havent got tag "bid-sent"',
                     "didnt": 'Contact didnt get tag "bid-sent"'}
        self.assertEqual(sorted(sentences), sorted(self.WIDENED))
        for word, cond in sentences.items():
            with self.assertRaises(SpecError, msg=cond) as cm:
                self._gate({"condition": cond, "tag": "bid-sent"})
            self.assertIn(repr(word), str(cm.exception).lower(), cond)
            # the same sentence without params.tag compiles to index-of-false
            self.assertEqual(self._ops(self._gate({"condition": cond})), [("index-of-false", ["bid-sent"])], cond)

    def test_widened_negative_words_inside_quoted_tag_names_do_not_trip(self):
        for word in self.WIDENED:
            tag = "{}-list".format(word)
            for cond in ('Contact has tag "{}"'.format(tag), "Contact has tag '{}'".format(tag)):
                self.assertEqual(self._ops(self._gate({"condition": cond, "tag": tag})),
                                 [("index-of-true", [tag])], cond)
                self.assertEqual(self._ops(self._gate({"condition": cond})), [("index-of-true", [tag])], cond)

    def test_widened_words_only_match_whole_words(self):
        for cond in ("Contact from Dontae's list has tag \"x\"", 'Contact with blacklist flag has tag "x"',
                     'Contact at Isntance Co has tag "x"'):
            self.assertEqual(self._ops(self._gate({"condition": cond, "tag": "x"})), [("index-of-true", ["x"])], cond)

    def test_negate_that_is_not_a_bool_or_null_is_an_error_naming_the_step(self):
        for negate in ("false", "no", "", "true", 0, 1, [], {}):
            for cond in ('Contact has tag "bid-sent"', 'Contact does not have tag "bid-sent"'):
                with self.assertRaises(SpecError, msg="{!r} {}".format(negate, cond)) as cm:
                    self._gate({"condition": cond, "tag": "bid-sent", "negate": negate})
                self.assertIn("'c'", str(cm.exception))
                self.assertIn("Check", str(cm.exception))
                self.assertIn("`negate` must be true, false or null", str(cm.exception))
        # also without params.tag
        with self.assertRaises(SpecError):
            self._gate({"condition": 'Contact has tag "bid-sent"', "negate": "false"})

    def test_negative_gate_error_names_the_word_and_the_fix(self):
        with self.assertRaises(SpecError) as cm:
            self._gate({"condition": 'Contact was never tagged "bid-sent"', "tag": "bid-sent"})
        msg = str(cm.exception)
        self.assertIn("'never'", msg)
        self.assertIn('set "negate": true, or "negate": false if the gate is a positive test '
                      '(straight quotes around tag names avoid false alarms)', msg)
        with self.assertRaises(SpecError) as cm:
            self._gate({"condition": 'Contact does not have tag "bid-sent"', "tag": "bid-sent"})
        self.assertIn("'does not'", str(cm.exception))


class TestExplicitNegateOnEveryGate(unittest.TestCase):
    """An explicit `negate` decides every gate, not only gates with params.tag;
    absent or null, the sentence is read as before."""

    _gate = TestTagStepGaps._gate

    def _ops(self, params):
        return [(c["conditionType"], c["conditionOperator"], c["conditionValue"])
                for c in self._gate(params)]

    def test_second_clause_negative_word_with_negate_false_compiles_positive(self):
        self.assertEqual(self._ops({"condition": 'Contact has tag "hot" (excluding test contacts)',
                                    "negate": False}),
                         [("contact_detail", "index-of-true", ["hot"])])
        for cond in ("Contact replied, excluding auto replies",
                     "Contact replied (don't count auto-replies)"):
            self.assertEqual(self._ops({"condition": cond, "negate": False}),
                             [("contact_reply", "==", "true")], cond)

    def test_negative_sentence_with_negate_false_compiles_positive(self):
        self.assertEqual(self._ops({"condition": 'Contact does not have tag "hot"', "negate": False}),
                         [("contact_detail", "index-of-true", ["hot"])])
        self.assertEqual(self._ops({"condition": "Contact has not replied", "negate": False}),
                         [("contact_reply", "==", "true")])

    def test_positive_sentence_with_negate_true_compiles_negative(self):
        self.assertEqual(self._ops({"condition": 'Contact has tag "hot"', "negate": True}),
                         [("contact_detail", "index-of-false", ["hot"])])
        self.assertEqual(self._ops({"condition": "Contact replied", "negate": True}),
                         [("contact_reply", "==", "false")])

    def test_absent_or_null_negate_still_reads_the_sentence(self):
        cases = [('Contact has tag "hot" (excluding test contacts)',
                  ("contact_detail", "index-of-false", ["hot"])),
                 ('Contact has tag "hot"', ("contact_detail", "index-of-true", ["hot"])),
                 ('Contact does not have tag "hot"', ("contact_detail", "index-of-false", ["hot"])),
                 ("Contact replied, excluding auto replies", ("contact_reply", "==", "false")),
                 ("Contact replied (don't count auto-replies)", ("contact_reply", "==", "false")),
                 ("Contact replied", ("contact_reply", "==", "true")),
                 ("Contact has not replied", ("contact_reply", "==", "false"))]
        for cond, expected in cases:
            for params in ({"condition": cond}, {"condition": cond, "negate": None}):
                self.assertEqual(self._ops(params), [expected], params)


if __name__ == "__main__":
    unittest.main()
