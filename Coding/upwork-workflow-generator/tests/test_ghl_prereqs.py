"""ghl_prereqs: derivation, dry run, apply, guards and id-map merge.

The HTTP layer is a fake in-memory sub-account; nothing touches the network.

    python3 -m pytest -q tests/test_ghl_prereqs.py
"""

import http.client
import io
import json
import os
import shutil
import socket
import sys
import tempfile
import unittest
import urllib.error
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from upwork_gen import compile_ghl  # noqa: E402
from upwork_gen import ghl_prereqs as gp  # noqa: E402

TOKEN = "pit-SECRET-token-1234567890"
LOC = "locTEST123"
CALCOM_SPEC_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "upwork-pipeline", "jobs", "cal-com-ghl-call-booked-pipeline", "spec.json")

# Self-contained copy of the GHL-relevant parts of the Cal.com spec, used when
# the job folder is not present.
CALCOM_SPEC = {
    "title": "Your Cal.com to Call Booked Pipeline System",
    "platform": "gohighlevel",
    "nodes": [
        {"key": "trigger", "kind": "trigger.app", "app": "ghl", "op": "contact_tag_added",
         "label": "1", "params": {"tag": "call-booked"}},
        {"key": "clear_cancel", "kind": "app.action", "app": "ghl", "op": "remove_tag",
         "label": "2", "params": {"tag": "call-cancelled"}},
        {"key": "opp", "kind": "app.action", "app": "ghl", "op": "create_opportunity", "label": "3",
         "params": {"pipeline": "Call Booked Pipeline", "stage": "Call Booked",
                    "name": "{{contact.first_name}} {{contact.last_name}} - Booked Call"}},
        {"key": "owner_email", "kind": "app.action", "app": "ghl", "op": "internal_notification",
         "label": "5", "params": {"type": "email", "message":
                                  "{{contact.call_time}} {{contact.email}} {{contact.call_notes}}"}},
        {"key": "goal", "kind": "app.action", "app": "ghl", "op": "goal", "label": "9",
         "params": {"goal_type": "tag_added", "tag": "call-cancelled"}},
        {"key": "opp_cancel", "kind": "app.action", "app": "ghl", "op": "update_opportunity",
         "label": "10", "params": {"pipeline": "Call Booked Pipeline", "stage": "Cancelled"}},
        {"key": "untag", "kind": "app.action", "app": "ghl", "op": "remove_tag", "label": "11",
         "params": {"tag": "call-booked"}},
        {"key": "rebook", "kind": "app.action", "app": "ghl", "op": "send_email", "label": "12",
         "params": {"subject": "Hi {{contact.first_name}}",
                    "body": "grab a time: {{custom_values.booking_link}}"}},
    ],
    "edges": [],
}


def calcom_spec():
    if os.path.exists(CALCOM_SPEC_PATH):
        with open(CALCOM_SPEC_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    return CALCOM_SPEC


class FakeGHL(object):
    """An in-memory sub-account that records every request."""

    def __init__(self, pipelines=None, tags=None, fields=None, values=None):
        self.pipelines = pipelines or []
        self.tags = tags or []
        self.fields = fields or []
        self.values = values or []
        self.calls = []
        self.n = 0

    def _id(self, prefix):
        self.n += 1
        return "{}{}".format(prefix, self.n)

    def __call__(self, method, url, headers, body):
        assert url.startswith(gp.BASE_URL)
        path = url[len(gp.BASE_URL):]
        data = json.loads(body.decode("utf-8")) if body else None
        self.calls.append((method, path, dict(headers), data))
        if method == "GET":
            if path.startswith("/opportunities/pipelines"):
                return 200, {"pipelines": self.pipelines}
            if path.endswith("/tags"):
                return 200, {"tags": self.tags}
            if "/customFields" in path:
                return 200, {"customFields": self.fields}
            if path.endswith("/customValues"):
                return 200, {"customValues": self.values}
        if method == "POST":
            if path == "/opportunities/pipelines":
                p = {"id": self._id("pipe"), "name": data["name"],
                     "stages": [{"id": self._id("stg"), "name": s["name"], "position": s["position"]}
                                for s in data["stages"]]}
                self.pipelines.append(p)
                return 200, p
            if path.endswith("/tags"):
                t = {"id": self._id("tag"), "name": data["name"]}
                self.tags.append(t)
                return 201, {"tag": t}
            if path.endswith("/customFields"):
                key = gp._snake(data["name"])
                f = dict(data, id=self._id("fld"), fieldKey="contact." + key)
                self.fields.append(f)
                return 201, {"customField": f}
            if path.endswith("/customValues"):
                key = gp._snake(data["name"])
                v = dict(data, id=self._id("cv"), fieldKey="{{ custom_values.%s }}" % key)
                self.values.append(v)
                return 201, {"customValue": v}
        return 404, {"message": "unexpected {} {}".format(method, path)}

    def writes(self):
        return [c for c in self.calls if c[0] != "GET"]


def full_account():
    """A sub-account that already has everything the Cal.com spec needs."""
    return FakeGHL(
        pipelines=[{"id": "P1", "name": "Call Booked Pipeline", "stages": [
            {"id": "S1", "name": "Call Booked"}, {"id": "S2", "name": "Cancelled"},
            {"id": "S3", "name": "Showed"}, {"id": "S4", "name": "No Show"}]}],
        tags=[{"id": "T1", "name": "call-booked"}, {"id": "T2", "name": "call-cancelled"}],
        fields=[{"id": "F1", "name": "Call Time", "fieldKey": "contact.call_time"},
                {"id": "F2", "name": "Call Notes", "fieldKey": "contact.call_notes"}],
        values=[{"id": "V1", "name": "Booking Link", "fieldKey": "{{ custom_values.booking_link }}"}])


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.catalog = os.path.join(self.tmp, "catalog")
        os.makedirs(self.catalog)
        self.env_path = os.path.join(self.tmp, ".env")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def write_spec(self, spec):
        path = os.path.join(self.tmp, "spec.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(spec, fh)
        return path

    def run_cli(self, fake, spec=None, extra=(), environ=None):
        out = io.StringIO()
        env = {"GHL_PIT_TOKEN": TOKEN, "GHL_LOCATION_ID": LOC} if environ is None else environ
        code = gp.run([self.write_spec(spec or calcom_spec())] + list(extra), transport=fake,
                      environ=env, env_path=self.env_path, catalog_dir=self.catalog, out=out)
        return code, out.getvalue()

    def id_map(self):
        with open(gp.id_map_path(LOC, self.catalog), "r", encoding="utf-8") as fh:
            return json.load(fh)


class TestDerive(unittest.TestCase):
    def test_calcom_spec(self):
        needs = gp.derive(calcom_spec())
        self.assertEqual(needs.tags, ["call-booked", "call-cancelled"])
        self.assertEqual(dict(needs.pipelines), {"Call Booked Pipeline": ["Call Booked", "Cancelled"]})
        self.assertEqual(needs.fields, ["call_time", "call_notes"])
        self.assertEqual(needs.custom_values, ["booking_link"])

    def test_if_else_tags_extra_stages_and_names(self):
        spec = {"nodes": [
            {"key": "g", "kind": "flow.branch", "params": {"condition": "contact tag includes \"bid-sent\""}},
            {"key": "o", "kind": "app.action", "app": "ghl", "op": "create_opportunity",
             "params": {"pipeline": "Demo", "stage": "New", "stages": ["New", "Won", "Lost"]}},
            {"key": "n", "kind": "app.action", "app": "ghl", "op": "send_sms",
             "params": {"message": "{{ contact.desired_service }} {{contact.company_name}}"}},
        ]}
        needs = gp.derive(spec)
        self.assertEqual(needs.tags, ["bid-sent"])
        self.assertEqual(needs.pipelines["Demo"], ["New", "Won", "Lost"])
        self.assertEqual(needs.fields, ["desired_service"])
        self.assertEqual(gp.display_name("call_time"), "Call Time")
        self.assertEqual(gp.field_data_type("call_notes"), "LARGE_TEXT")
        self.assertEqual(gp.field_data_type("call_time"), "TEXT")


class TestRun(Base):
    def test_dry_run_makes_no_writes(self):
        fake = FakeGHL()
        code, out = self.run_cli(fake)
        self.assertEqual(code, 1)
        self.assertEqual(fake.writes(), [])
        self.assertIn("will create", out)
        self.assertIn("--apply", out)

    def test_apply_creates_only_missing(self):
        fake = FakeGHL(tags=[{"id": "T1", "name": "call-booked"}],
                       fields=[{"id": "F1", "name": "Call Time", "fieldKey": "contact.call_time"}])
        code, out = self.run_cli(fake, extra=["--apply"])
        self.assertEqual(code, 0, out)
        writes = [(m, p, d) for m, p, _h, d in fake.writes()]
        self.assertEqual([w for w in writes if w[0] != "POST"], [])
        paths = sorted(p for _m, p, _d in writes)
        self.assertEqual(paths, sorted([
            "/opportunities/pipelines",
            "/locations/{}/tags".format(LOC),
            "/locations/{}/customFields".format(LOC),
            "/locations/{}/customValues".format(LOC)]))
        bodies = {p: d for _m, p, d in writes}
        self.assertEqual(bodies["/locations/{}/tags".format(LOC)], {"name": "call-cancelled"})
        self.assertEqual(bodies["/locations/{}/customFields".format(LOC)],
                         {"name": "Call Notes", "dataType": "LARGE_TEXT", "model": "contact"})
        self.assertEqual(bodies["/locations/{}/customValues".format(LOC)],
                         {"name": "Booking Link", "value": "PASTE-YOUR-VALUE"})
        self.assertEqual(bodies["/opportunities/pipelines"], {
            "name": "Call Booked Pipeline", "locationId": LOC,
            "stages": [{"name": "Call Booked", "position": 0}, {"name": "Cancelled", "position": 1}]})
        pipe_hdr = [h for m, p, h, _d in fake.writes() if p == "/opportunities/pipelines"][0]
        self.assertEqual(pipe_hdr["Version"], "v3")
        ids = self.id_map()
        self.assertIn("pipeline:Call Booked Pipeline", ids)
        self.assertIn("stage:Call Booked Pipeline/Cancelled", ids)
        self.assertIn("custom_value:Booking Link", ids)
        self.assertIn("field:Call Notes", ids)

    def test_everything_exists_exit_zero(self):
        fake = full_account()
        code, out = self.run_cli(fake, extra=["--apply"])
        self.assertEqual(code, 0, out)
        self.assertEqual(fake.writes(), [])
        self.assertIn("everything the spec needs exists", out)

    def test_sales_guard(self):
        spec = {"title": "x", "nodes": [{"key": "o", "kind": "app.action", "app": "ghl",
                                         "op": "create_opportunity",
                                         "params": {"pipeline": "Sales", "stage": "Won"}}]}
        fake = FakeGHL()
        code, out = self.run_cli(fake, spec=spec, extra=["--apply"])
        self.assertEqual(code, 2)
        self.assertIn("demo pipeline", out)
        self.assertEqual(fake.calls, [])

    def test_missing_stage_on_existing_pipeline(self):
        fake = full_account()
        fake.pipelines[0]["stages"] = [s for s in fake.pipelines[0]["stages"] if s["name"] != "Cancelled"]
        code, out = self.run_cli(fake, extra=["--apply"])
        self.assertEqual(code, 3)
        self.assertIn("add stage 'Cancelled' to pipeline 'Call Booked Pipeline' by hand", out)
        self.assertEqual([c for c in fake.writes() if "pipelines" in c[1]], [])
        self.assertEqual(fake.writes(), [])

    def test_id_map_merge_keeps_old_keys(self):
        path = gp.id_map_path(LOC, self.catalog)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"_about": "hand map", "workflow:Old": "W1", "tag:call-booked": "STALE"}, fh)
        code, _out = self.run_cli(full_account())
        self.assertEqual(code, 0)
        ids = self.id_map()
        self.assertEqual(ids["_about"], "hand map")
        self.assertEqual(ids["workflow:Old"], "W1")
        self.assertEqual(ids["tag:call-booked"], "T1")
        self.assertEqual(ids["stage:Call Booked Pipeline/No Show"], "S4")
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
        self.assertEqual(text, json.dumps(ids, indent=2, sort_keys=True) + "\n")

    def test_missing_token_exit_2(self):
        code, out = self.run_cli(FakeGHL(), environ={})
        self.assertEqual(code, 2)
        self.assertIn("GHL_PIT_TOKEN", out)
        self.assertEqual(len(out.strip().splitlines()), 1)

    def test_token_from_env_file_and_default_location(self):
        with open(self.env_path, "w") as fh:
            fh.write("GHL_PIT_TOKEN=\"{}\"\n".format(TOKEN))
        fake = FakeGHL()
        self.run_cli(fake, environ={})
        self.assertTrue(fake.calls)
        self.assertEqual(fake.calls[0][2]["Authorization"], "Bearer " + TOKEN)
        self.assertIn(gp.DEFAULT_LOCATION, fake.calls[1][1])

    def test_token_never_in_output(self):
        code, out = self.run_cli(FakeGHL(), extra=["--apply"])
        self.assertNotIn(TOKEN, out)

        def echo(method, url, headers, body):
            return 401, {"message": "bad token " + headers["Authorization"]}
        code, out = self.run_cli(echo)
        self.assertEqual(code, 1)
        self.assertNotIn(TOKEN, out)
        self.assertIn("<GHL_PIT_TOKEN>", out)



def _opp(key, pipeline, stage=None, stages=None, op="create_opportunity"):
    params = {"pipeline": pipeline}
    if stage is not None:
        params["stage"] = stage
    if stages is not None:
        params["stages"] = stages
    return {"key": key, "kind": "app.action", "app": "ghl", "op": op, "params": params}


def _spec(*nodes):
    return {"title": "t", "nodes": list(nodes), "edges": []}


class TestStageOrder(Base):
    """Defect 1: an explicit `stages` list sets the order."""

    def test_stages_list_wins_over_stage_param(self):
        spec = _spec(_opp("a", "Demo", stage="Cancelled"),
                     _opp("b", "Demo", stage="Won", stages=["New", "Won", "Lost"]),
                     _opp("c", "Demo", stage="New", op="update_opportunity"))
        self.assertEqual(gp.derive(spec).pipelines["Demo"], ["New", "Won", "Lost", "Cancelled"])

    def test_created_pipeline_uses_listed_order(self):
        spec = _spec(_opp("b", "Demo", stage="Won", stages=["New", "Won", "Lost"]))
        fake = FakeGHL()
        code, out = self.run_cli(fake, spec=spec, extra=["--apply"])
        self.assertEqual(code, 0, out)
        body = [d for _m, p, _h, d in fake.writes() if p == "/opportunities/pipelines"][0]
        self.assertEqual(body["stages"], [{"name": "New", "position": 0}, {"name": "Won", "position": 1},
                                          {"name": "Lost", "position": 2}])

    def test_stages_not_a_list_exit_2(self):
        fake = FakeGHL()
        code, out = self.run_cli(fake, spec=_spec(_opp("b", "Demo", stage="Won", stages="New, Won")),
                                 extra=["--apply"])
        self.assertEqual(code, 2)
        self.assertIn("`stages` must be a list", out)
        self.assertEqual(fake.calls, [])

    def test_stages_entry_not_a_string_exit_2(self):
        with self.assertRaises(gp.ConfigError):
            gp.derive(_spec(_opp("b", "Demo", stages=["New", {"name": "Won"}])))


class TestExactNames(Base):
    """Defect 2: names match exactly, as compile_ghl looks them up."""

    def test_pipeline_differing_by_case_is_a_hand_fix(self):
        fake = full_account()
        fake.pipelines[0]["name"] = "call booked pipeline"
        code, out = self.run_cli(fake, extra=["--apply"])
        self.assertEqual(code, 3, out)
        self.assertIn("NAME MISMATCH", out)
        self.assertIn("GHL has pipeline 'call booked pipeline'", out)
        self.assertIn("rename it in GHL or change the spec", out)
        self.assertEqual([c for c in fake.writes() if "pipelines" in c[1]], [])
        self.assertEqual(len(fake.pipelines), 1)

    def test_pipeline_differing_by_spacing_is_a_hand_fix(self):
        fake = full_account()
        fake.pipelines[0]["name"] = "Call  Booked Pipeline "
        code, out = self.run_cli(fake, extra=["--apply"])
        self.assertEqual(code, 3, out)
        self.assertEqual(fake.writes(), [])

    def test_stage_differing_by_case_is_a_hand_fix(self):
        fake = full_account()
        fake.pipelines[0]["stages"][1]["name"] = "cancelled"
        code, out = self.run_cli(fake, extra=["--apply"])
        self.assertEqual(code, 3, out)
        self.assertIn("has stage 'cancelled', which differs from the spec's 'Cancelled'", out)
        self.assertEqual(fake.writes(), [])

    def test_spec_spelling_one_pipeline_two_ways_exit_2(self):
        fake = FakeGHL()
        code, out = self.run_cli(fake, spec=_spec(_opp("a", "Demo", stage="New"),
                                                  _opp("b", "demo ", stage="Won")), extra=["--apply"])
        self.assertEqual(code, 2)
        self.assertIn("'Demo' and 'demo '", out)
        self.assertEqual(fake.calls, [])

    def test_spec_spelling_one_stage_two_ways_exit_2(self):
        with self.assertRaises(gp.ConfigError):
            gp.validate(gp.derive(_spec(_opp("a", "Demo", stage="Won"), _opp("b", "Demo", stage="won"))))

    def test_look_alike_names_are_hand_fixes_not_near_duplicates(self):
        """Max-2 should-fix: a name that differs only by fullwidth letters or
        zero-width characters is a near-miss (exit 3), never a second object."""
        spec = _spec(_opp("o", "Demo", stage="Won"))
        for ghl_name in ("Ｄｅｍｏ", "Demo\u200b", "De\u00admo"):
            fake = FakeGHL(pipelines=[{"id": "P1", "name": ghl_name, "stages": [{"id": "S1", "name": "Won"}]}])
            code, out = self.run_cli(fake, spec=spec, extra=["--apply"])
            self.assertEqual(code, 3, (ghl_name, out))
            self.assertIn("NAME MISMATCH", out)
            self.assertEqual(fake.writes(), [], repr(ghl_name))
        for ghl_stage in ("Ｗｏｎ", "Won\u200b"):
            fake = FakeGHL(pipelines=[{"id": "P1", "name": "Demo",
                                       "stages": [{"id": "S1", "name": ghl_stage}]}])
            code, out = self.run_cli(fake, spec=spec, extra=["--apply"])
            self.assertEqual(code, 3, (ghl_stage, out))
            self.assertIn("which differs from the spec's 'Won' only by case, spacing or look-alike "
                          "characters", out)
            self.assertEqual(fake.writes(), [], repr(ghl_stage))
        # One spec spelling the same pipeline two look-alike ways is exit 2.
        # The plain-ASCII check names the look-alike first (max-3 re-review,
        # item 2); check_spec_names still refuses the pair on its own.
        fake = FakeGHL()
        spec = _spec(_opp("a", "Demo", stage="Won"), _opp("b", "Demo\u200b", stage="Won"))
        code, out = self.run_cli(fake, spec=spec, extra=["--apply"])
        self.assertEqual(code, 2, out)
        self.assertIn("pipeline 'Demo\\u200b' (node 'b'): GHL names in a spec must be plain ASCII", out)
        self.assertEqual(fake.calls, [])
        with self.assertRaises(gp.ConfigError) as ctx:
            gp.check_spec_names(gp.derive(spec))
        self.assertIn("the spec spells one pipeline", str(ctx.exception))

    def test_same_pipeline_in_many_nodes_is_created_once(self):
        fake = FakeGHL()
        spec = _spec(_opp("a", "Demo", stage="New"), _opp("b", "Demo", stage="Won", op="update_opportunity"))
        code, out = self.run_cli(fake, spec=spec, extra=["--apply"])
        self.assertEqual(code, 0, out)
        self.assertEqual(len([c for c in fake.writes() if c[1] == "/opportunities/pipelines"]), 1)
        self.assertIn("stage:Demo/Won", self.id_map())


class TestIdMapWrite(Base):
    """Defect 3: atomic write; a non-object map is refused before any write."""

    def test_map_not_an_object_exit_2_without_writing(self):
        path = gp.id_map_path(LOC, self.catalog)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write('["not", "a", "map"]\n')
        fake = FakeGHL()
        code, out = self.run_cli(fake, extra=["--apply"])
        self.assertEqual(code, 2)
        self.assertIn("not a JSON object", out)
        self.assertEqual(fake.writes(), [])
        with open(path, "r", encoding="utf-8") as fh:
            self.assertEqual(fh.read(), '["not", "a", "map"]\n')

    def test_failed_write_keeps_the_original(self):
        path = gp.id_map_path(LOC, self.catalog)
        original = json.dumps({"workflow:Old": "W1"}, indent=2) + "\n"
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(original)

        def broken_dump(obj, fh, **kwargs):
            fh.write('{"partial": ')
            raise OSError("disk full")

        spec_path = self.write_spec(calcom_spec())
        buf = io.StringIO()
        with mock.patch.object(gp.json, "dump", side_effect=broken_dump):
            with self.assertRaises(gp.IdMapWriteError):
                gp.refresh_id_map(path, gp.State([], [{"id": "T1", "name": "x"}], [], []))
            code = gp.run([spec_path], transport=full_account(),
                          environ={"GHL_PIT_TOKEN": TOKEN, "GHL_LOCATION_ID": LOC},
                          env_path=self.env_path, catalog_dir=self.catalog, out=buf)
        out = buf.getvalue()
        self.assertEqual(code, 1)  # an id-map write failure is exit 1 (module docstring)
        self.assertIn("disk full", out)
        with open(path, "r", encoding="utf-8") as fh:
            self.assertEqual(fh.read(), original)
        self.assertEqual(os.listdir(self.catalog), [os.path.basename(path)])

    def test_write_is_sorted_two_space_and_replaces(self):
        path = gp.id_map_path(LOC, self.catalog)
        gp.refresh_id_map(path, gp.State([], [{"id": "T2", "name": "b"}, {"id": "T1", "name": "a"}], [], []))
        with open(path, "r", encoding="utf-8") as fh:
            self.assertEqual(fh.read(), '{\n  "tag:a": "T1",\n  "tag:b": "T2"\n}\n')
        self.assertEqual(os.listdir(self.catalog), [os.path.basename(path)])


class LossyGHL(FakeGHL):
    """Answers tag creates with 201 but never stores the tag."""

    def __call__(self, method, url, headers, body):
        if method == "POST" and url.endswith("/tags"):
            self.calls.append((method, url[len(gp.BASE_URL):], dict(headers), json.loads(body.decode("utf-8"))))
            return 201, {"tag": {"id": "lost", "name": "lost"}}
        return FakeGHL.__call__(self, method, url, headers, body)


class FailingGHL(FakeGHL):
    """Fails every custom value create with HTTP 500."""

    def __call__(self, method, url, headers, body):
        if method == "POST" and url.endswith("/customValues"):
            return 500, {"message": "internal error"}
        return FakeGHL.__call__(self, method, url, headers, body)


class TestApplyChecks(Base):
    """Defect 4: re-plan after --apply, key validation, part-way failures."""

    def test_apply_rechecks_and_exits_1_when_still_missing(self):
        fake = LossyGHL()
        code, out = self.run_cli(fake, extra=["--apply"])
        self.assertEqual(code, 1, out)
        self.assertIn("still missing after --apply: tag 'call-booked', tag 'call-cancelled'", out)
        self.assertNotIn("everything the spec needs exists", out)

    def test_camel_case_field_key_exit_2_before_any_call(self):
        spec = _spec({"key": "n", "kind": "app.action", "app": "ghl", "op": "send_sms",
                      "params": {"message": "at {{contact.callTime}}"}})
        fake = FakeGHL()
        code, out = self.run_cli(fake, spec=spec, extra=["--apply"])
        self.assertEqual(code, 2)
        self.assertIn("field key 'callTime'", out)
        self.assertIn("lowercases", out)
        self.assertIn("{{contact.call_time}}", out)
        self.assertEqual(fake.calls, [])

    def test_bad_custom_value_and_named_field_keys_exit_2(self):
        spec = _spec({"key": "n", "kind": "app.action", "app": "ghl", "op": "send_sms",
                      "params": {"message": "{{custom_values.Booking-Link}}"}},
                     {"key": "u", "kind": "app.action", "app": "ghl", "op": "update_contact_field",
                      "params": {"field": "contact.leadScore", "value": "1"}})
        fake = FakeGHL()
        code, out = self.run_cli(fake, spec=spec, extra=["--apply"])
        self.assertEqual(code, 2)
        self.assertIn("custom value key 'Booking-Link'", out)
        self.assertIn("{{custom_values.booking_link}}", out)
        self.assertIn("field key 'leadScore'", out)
        self.assertEqual(fake.calls, [])

    def test_part_way_failure_lists_what_was_created(self):
        fake = FailingGHL()
        code, out = self.run_cli(fake, extra=["--apply"])
        self.assertEqual(code, 1, out)
        self.assertIn("--apply stopped part-way", out)
        self.assertIn("HTTP 500", out)
        self.assertIn("already created before the error: tag 'call-booked', tag 'call-cancelled', "
                      "pipeline 'Call Booked Pipeline', field 'call_time', field 'call_notes'", out)
        self.assertNotIn(TOKEN, out)
        # Max-3 re-review, item 1: a 5xx may come after GHL saved it.
        self.assertIn("possibly created: custom_value 'booking_link' was in flight; GHL may hold it; a dry "
                      "run shows which.", out)

    def test_first_create_failing_says_nothing_created(self):
        def fail_posts(method, url, headers, body):
            if method == "POST":
                return 400, {"message": "nope"}  # a 4xx: GHL refused it (a 5xx is in flight)
            return FakeGHL()(method, url, headers, body)
        code, out = self.run_cli(fail_posts, extra=["--apply"])
        self.assertEqual(code, 1)
        self.assertIn("nothing was created before the error", out)
        self.assertNotIn("possibly created", out)


class TestErrors(Base):
    def test_token_straddling_the_cut_point_is_redacted(self):
        """Defect 5: redact first, then truncate."""
        def echo(method, url, headers, body):
            return 401, "x" * (gp.DETAIL_LIMIT - 10) + headers["Authorization"] + " trailing"
        code, out = self.run_cli(echo)
        self.assertEqual(code, 1)
        self.assertNotIn(TOKEN[:10], out)
        self.assertNotIn(TOKEN, out)

    def test_network_errors_exit_1(self):
        for exc in (urllib.error.URLError("timed out"), socket.timeout("read timed out"),
                    ConnectionResetError("reset")):
            def down(method, url, headers, body, exc=exc):
                raise exc
            code, out = self.run_cli(down)
            self.assertEqual(code, 1, out)
            self.assertIn("network error", out)
            self.assertNotIn(TOKEN, out)

    def test_sales_guard_any_case_and_spacing(self):
        for name in ("SALES", " sales "):
            fake = FakeGHL()
            code, out = self.run_cli(fake, spec=_spec(_opp("o", name, stage="Won")), extra=["--apply"])
            self.assertEqual(code, 2, name)
            self.assertIn("demo pipeline", out)
            self.assertEqual(fake.calls, [])
        with self.assertRaises(gp.ConfigError):
            gp.GHLClient(TOKEN, LOC, FakeGHL()).create_pipeline(" SALES ", ["Won"])

    def test_sales_guard_look_alikes(self):
        """Max-2 should-fix: zero-width characters and fullwidth letters used to
        get past the guard ("Sales" + U+200B was created, exit 0)."""
        for name in ("Sales\u200b", "\u200bSales", "Sa\u200cles", "Sal\u200des", "Sales\u2060",
                     "\ufeffSales", "Sa\u00adles", "\u034fSales", "ＳＡＬＥＳ", "Ｓａｌｅｓ",
                     "ｓａｌｅｓ\u200b", "Sales\u3000", " S\u200dALES\u00a0"):
            self.assertEqual(gp._norm(name), "sales", repr(name))
            fake = FakeGHL()
            code, out = self.run_cli(fake, spec=_spec(_opp("o", name, stage="Won")), extra=["--apply"])
            self.assertEqual(code, 2, (name, out))
            self.assertIn("demo pipeline", out)
            self.assertEqual(fake.calls, [], repr(name))
            with self.assertRaises(gp.ConfigError):
                gp.GHLClient(TOKEN, LOC, FakeGHL()).create_pipeline(name, ["Won"])
        # A pipeline whose name only contains the word is not the guarded one.
        gp.validate(gp.derive(_spec(_opp("o", "Sales Demo", stage="Won"))))

    def test_nodes_not_a_list_exit_2_before_any_call(self):
        """Max-2 should-fix: `"nodes": null` was an uncaught TypeError."""
        for nodes in (None, {"n": {"key": "n"}}, "nodes", 5):
            fake = FakeGHL()
            code, out = self.run_cli(fake, spec={"title": "t", "nodes": nodes, "edges": []}, extra=["--apply"])
            self.assertEqual(code, 2, (nodes, out))
            self.assertIn("the spec's `nodes` must be a list of steps", out)
            self.assertEqual(fake.calls, [], nodes)

    def test_pipeline_without_stages_exit_2(self):
        spec = _spec({"key": "t", "kind": "trigger.app", "app": "ghl", "op": "pipeline_stage_changed",
                      "params": {"pipeline": "Demo"}})
        fake = FakeGHL()
        code, out = self.run_cli(fake, spec=spec, extra=["--apply"])
        self.assertEqual(code, 2)
        self.assertIn("needs at least one stage", out)
        self.assertEqual(fake.writes(), [])
        fake = FakeGHL(pipelines=[{"id": "P9", "name": "Demo", "stages": [{"id": "S9", "name": "New"}]}])
        code, out = self.run_cli(fake, spec=spec)
        self.assertEqual(code, 0, out)

    def test_standard_merge_fields_are_not_created(self):
        spec = _spec({"key": "n", "kind": "app.action", "app": "ghl", "op": "send_sms",
                      "params": {"message": "{{contact.id}} {{contact.phone_raw}} {{contact.full_address}}"}})
        self.assertEqual(gp.derive(spec).fields, [])


class TestFieldDerivation(Base):
    """Defect 6: fields named by update_contact_field and AI output_field."""

    SPEC = _spec(
        {"key": "u1", "kind": "app.action", "app": "ghl", "op": "update_contact_field",
         "params": {"field": "Lead Score", "value": "10"}},
        {"key": "u2", "kind": "app.action", "app": "ghl", "op": "update_contact_field",
         "params": {"field": "Email", "value": "x"}},
        {"key": "u3", "kind": "app.action", "app": "ghl", "op": "update_contact_field",
         "params": {"field": "contact.budget", "value": "x"}},
        {"key": "a1", "kind": "app.action", "app": "ghl", "op": "ai_step",
         "params": {"prompt": "sum up", "output_field": "ai_summary"}},
        {"key": "a2", "kind": "ai.llm", "label": "Classify",
         "params": {"prompt": "classify", "output_field": "{{contact.lead_intent}}"}},
        {"key": "a3", "kind": "ai.agent", "label": "Agent",
         "params": {"prompt": "go", "output_field": "Agent Notes"}},
    )

    def test_derived(self):
        needs = gp.derive(self.SPEC)
        self.assertEqual(needs.fields, ["budget", "ai_summary", "lead_intent"])
        self.assertEqual(needs.field_names, ["Lead Score", "Agent Notes"])

    def test_name_that_matches_a_key_is_one_field(self):
        spec = _spec({"key": "u", "kind": "app.action", "app": "ghl", "op": "update_contact_field",
                      "params": {"field": "Call Notes", "value": "{{contact.call_notes}}"}})
        needs = gp.derive(spec)
        self.assertEqual((needs.fields, needs.field_names), (["call_notes"], []))

    def test_existing_fields_match_by_name_and_key(self):
        fake = FakeGHL(fields=[{"id": "F1", "name": "lead score", "fieldKey": "contact.lead_score"},
                               {"id": "F2", "name": "AI Summary Text", "fieldKey": "contact.ai_summary"}])
        code, out = self.run_cli(fake, spec=self.SPEC, extra=["--apply"])
        self.assertEqual(code, 0, out)
        created = sorted(d["name"] for _m, p, _h, d in fake.writes() if p.endswith("/customFields"))
        self.assertEqual(created, ["Agent Notes", "Budget", "Lead Intent"])
        agent = [d for _m, p, _h, d in fake.writes() if d and d.get("name") == "Agent Notes"][0]
        self.assertEqual(agent["dataType"], "LARGE_TEXT")


class TestSharedConditionTags(unittest.TestCase):
    """Defect 6: one tag reader for compile_ghl and ghl_prereqs."""

    def test_same_function(self):
        self.assertIs(gp.condition_tags, compile_ghl.condition_tags)

    def _branch(self, **params):
        return _spec({"key": "g", "kind": "flow.branch", "params": params})

    def test_only_tag_predicate_quotes_count(self):
        cond = "contact tag includes \"bid-sent\" and opportunity stage is \"Won\""
        self.assertEqual(gp.derive(self._branch(condition=cond)).tags, ["bid-sent"])
        self.assertEqual(compile_ghl._tag_condition({"condition": cond}), (["bid-sent"], False))

    def test_params_tag_string_and_list(self):
        self.assertEqual(gp.derive(self._branch(tag="vip")).tags, ["vip"])
        self.assertEqual(gp.derive(self._branch(tag=["a", "b"], condition="whatever")).tags, ["a", "b"])

    def test_single_and_double_quotes(self):
        self.assertEqual(gp.derive(self._branch(condition="contact doesn't have tag 'vip'")).tags, ["vip"])
        self.assertEqual(gp.derive(self._branch(condition="tag is \"a\", 'b' or \"c\"")).tags, ["a", "b", "c"])
        self.assertEqual(compile_ghl._tag_condition({"condition": "contact doesn't have tag 'vip'"}),
                         (["vip"], True))

    def test_no_tag_predicate_no_tags(self):
        self.assertEqual(gp.derive(self._branch(condition="opportunity stage is \"Won\"")).tags, [])
        self.assertIsNone(compile_ghl._tag_condition({"condition": "opportunity stage is \"Won\""}))


class TestKeyRoundTrip(Base):
    """Re-review defect 1: a key must survive _snake(display_name(key))."""

    CASES = (("call__time", "call_time"), ("_score", "score"), ("score_", "score"),
             ("booking__link", "booking_link"))

    def test_bad_field_keys_exit_2_before_any_call(self):
        for key, fixed in self.CASES:
            self.assertNotEqual(gp._snake(gp.display_name(key)), key)
            fake = FakeGHL()
            spec = _spec({"key": "n", "kind": "app.action", "app": "ghl", "op": "send_sms",
                          "params": {"message": "at {{contact.%s}}" % key}})
            code, out = self.run_cli(fake, spec=spec, extra=["--apply"])
            self.assertEqual(code, 2, key)
            self.assertIn("field key {!r}".format(key), out)
            self.assertIn("{{contact.%s}}." % fixed, out)
            self.assertEqual(fake.calls, [], key)

    def test_bad_custom_value_keys_exit_2_before_any_call(self):
        for key, fixed in self.CASES:
            fake = FakeGHL()
            spec = _spec({"key": "n", "kind": "app.action", "app": "ghl", "op": "send_sms",
                          "params": {"message": "{{custom_values.%s}}" % key}})
            code, out = self.run_cli(fake, spec=spec, extra=["--apply"])
            self.assertEqual(code, 2, key)
            self.assertIn("custom value key {!r}".format(key), out)
            self.assertIn("{{custom_values.%s}}." % fixed, out)
            self.assertEqual(fake.calls, [], key)

    def test_bad_key_named_by_field_param_exit_2(self):
        for field in ("call__time", "contact._score"):
            fake = FakeGHL()
            spec = _spec({"key": "u", "kind": "app.action", "app": "ghl", "op": "update_contact_field",
                          "params": {"field": field, "value": "1"}})
            code, out = self.run_cli(fake, spec=spec, extra=["--apply"])
            self.assertEqual(code, 2, field)
            self.assertIn("field key", out)
            self.assertEqual(fake.calls, [], field)

    def test_good_keys_still_pass(self):
        for key in ("call_time", "call2_time", "score"):
            self.assertEqual(gp._snake(gp.display_name(key)), key)
            spec = _spec({"key": "n", "kind": "app.action", "app": "ghl", "op": "send_sms",
                          "params": {"message": "{{contact.%s}} {{custom_values.%s}}" % (key, key)}})
            needs = gp.derive(spec)
            gp.validate(needs)
            self.assertEqual((needs.fields, needs.custom_values), ([key], [key]))


class GetFailsAfterCreates(FakeGHL):
    """Creates succeed; every GET after the first POST answers HTTP 503."""

    def __call__(self, method, url, headers, body):
        if method == "GET" and self.writes():
            self.calls.append((method, url[len(gp.BASE_URL):], dict(headers), None))
            return 503, {"message": "unavailable"}
        return FakeGHL.__call__(self, method, url, headers, body)


class TestFailureAfterCreates(Base):
    """Re-review defect 2: every failure after a create lists what was made."""

    CREATED = ("already created before the error: tag 'call-booked', tag 'call-cancelled', "
               "pipeline 'Call Booked Pipeline', field 'call_time', field 'call_notes', "
               "custom_value 'booking_link'")

    def assert_created_listed_first(self, out):
        self.assertIn(self.CREATED, out)
        self.assertLess(out.index(self.CREATED), out.index("error after the creates"))
        self.assertIn("rerun to finish", out)
        self.assertNotIn(TOKEN, out)

    def test_get_fails_after_creates(self):
        fake = GetFailsAfterCreates()
        code, out = self.run_cli(fake, extra=["--apply"])
        self.assertEqual(code, 1, out)
        self.assert_created_listed_first(out)
        self.assertIn("HTTP 503", out)
        self.assertEqual(len(fake.writes()), 6)

    def test_id_map_write_fails_after_creates(self):
        fake = FakeGHL()
        with mock.patch.object(gp, "write_json_atomic", side_effect=OSError("disk full")):
            code, out = self.run_cli(fake, extra=["--apply"])
        self.assertEqual(code, 1, out)
        self.assert_created_listed_first(out)
        self.assertIn("could not write the id map", out)
        self.assertIn("disk full", out)
        self.assertEqual(len(fake.writes()), 6)

    def test_replan_exception_after_creates(self):
        fake = FakeGHL()
        real_plan = gp.plan
        calls = []

        def plan_then_fail(needs, state):
            calls.append(1)
            if len(calls) > 1:
                raise KeyError("stages")
            return real_plan(needs, state)

        with mock.patch.object(gp, "plan", side_effect=plan_then_fail):
            code, out = self.run_cli(fake, extra=["--apply"])
        self.assertEqual(code, 1, out)
        self.assert_created_listed_first(out)
        self.assertIn("KeyError", out)

    def test_dry_run_map_write_failure_exit_1_nothing_created(self):
        with mock.patch.object(gp, "write_json_atomic", side_effect=OSError("disk full")):
            code, out = self.run_cli(full_account())
        self.assertEqual(code, 1, out)
        self.assertIn("could not write the id map", out)
        self.assertNotIn("already created", out)


class TestFailClosedReads(Base):
    """Re-review defect 4: a 2xx read that is not the expected list is an error."""

    def _serving(self, bad_path_part, answer):
        fake = FakeGHL()

        def transport(method, url, headers, body):
            if method == "GET" and bad_path_part in url:
                fake.calls.append((method, url, dict(headers), None))
                return 200, answer
            return fake(method, url, headers, body)
        return fake, transport

    def test_bad_2xx_reads_exit_1_without_writes(self):
        answers = ("<html><body>Please log in</body></html>", {}, {"message": "ok"},
                   {"pipelines": None, "tags": None, "customFields": None, "customValues": None},
                   {"pipelines": "x", "tags": "x", "customFields": "x", "customValues": "x"},
                   {"pipelines": ["x"], "tags": ["x"], "customFields": ["x"], "customValues": ["x"]},
                   [])
        for part, key in (("/opportunities/pipelines", "pipelines"), ("/tags", "tags"),
                          ("/customFields", "customFields"), ("/customValues", "customValues")):
            for answer in answers:
                fake, transport = self._serving(part, answer)
                code, out = self.run_cli(transport, extra=["--apply"])
                self.assertEqual(code, 1, (part, answer, out))
                self.assertIn("not a JSON object with a `{}` list".format(key), out)
                self.assertEqual(fake.writes(), [], (part, answer))
                self.assertFalse(os.path.exists(gp.id_map_path(LOC, self.catalog)))

    def test_client_reads_raise(self):
        client = gp.GHLClient(TOKEN, LOC, lambda m, u, h, b: (200, "<html>" + h["Authorization"]))
        for read in (client.pipelines, client.tags, client.custom_fields, client.custom_values):
            with self.assertRaises(gp.GHLError) as ctx:
                read()
            self.assertNotIn(TOKEN, str(ctx.exception))

    def test_empty_lists_are_fine(self):
        code, out = self.run_cli(FakeGHL())
        self.assertEqual(code, 1, out)
        self.assertIn("to create", out)

    def test_objects_without_a_string_name_exit_1_without_writes(self):
        """Round-4 should-fix: an object with no string `name` is a bad read."""
        for part, key in (("/opportunities/pipelines", "pipelines"), ("/tags", "tags"),
                          ("/customFields", "customFields"), ("/customValues", "customValues")):
            for item in ({"id": "X1"}, {"id": "X1", "name": None}, {"id": "X1", "name": 5},
                         {"id": "X1", "name": {"text": "Call Booked Pipeline"}}):
                fake, transport = self._serving(part, {key: [item]})
                code, out = self.run_cli(transport, extra=["--apply"])
                self.assertEqual(code, 1, (part, item, out))
                self.assertIn("an object in `{}` has no string `name`".format(key), out)
                self.assertEqual(fake.writes(), [], (part, item))
                self.assertFalse(os.path.exists(gp.id_map_path(LOC, self.catalog)))
                self.assertNotIn(TOKEN, out)


class TestAccountStagesShape(Base):
    """Round-4 should-fix: a GHL pipeline whose `stages` is not a list of named
    stages is a clean exit 2 before any write, never a traceback."""

    BAD_STAGES = ("New", {"New": 1}, [1, 2], ["New"], [{"id": "S1"}], [{"id": "S1", "name": 5}])

    def test_bad_stages_exit_2_without_writes(self):
        for stages in self.BAD_STAGES:
            for name in ("Call Booked Pipeline", "Some Other Pipeline"):  # used by the spec or not
                fake = full_account()
                fake.pipelines.append({"id": "P9", "name": name, "stages": stages})
                if name == "Call Booked Pipeline":
                    fake.pipelines.pop(0)
                code, out = self.run_cli(fake, extra=["--apply"])
                self.assertEqual(code, 2, (stages, name, out))
                self.assertIn("GHL pipeline {!r} has a `stages` value that is not a list of named "
                              "stages".format(name), out)
                self.assertEqual(fake.writes(), [], (stages, name))
                self.assertFalse(os.path.exists(gp.id_map_path(LOC, self.catalog)))

    def test_null_or_missing_stages_still_read(self):
        fake = full_account()
        fake.pipelines.append({"id": "P9", "name": "Other", "stages": None})
        fake.pipelines.append({"id": "P8", "name": "Another"})
        code, out = self.run_cli(fake)
        self.assertEqual(code, 0, out)

    def test_bad_stages_after_a_create_lists_what_was_created(self):
        class BrokenStagesAfterCreate(FakeGHL):
            def __call__(self, method, url, headers, body):
                code, payload = FakeGHL.__call__(self, method, url, headers, body)
                if method == "POST" and url.endswith("/opportunities/pipelines"):
                    self.pipelines[-1]["stages"] = "broken"
                return code, payload

        fake = BrokenStagesAfterCreate()
        code, out = self.run_cli(fake, extra=["--apply"])
        self.assertEqual(code, 1, out)
        self.assertIn("already created before the error: tag 'call-booked', tag 'call-cancelled', "
                      "pipeline 'Call Booked Pipeline'", out)
        self.assertIn("error after the creates", out)
        self.assertIn("has a `stages` value that is not a list of named stages", out)


class TestAnyCreateFailure(Base):
    """Round-4 should-fix: any exception during a create lists what was created."""

    class RaisesOnFields(FakeGHL):
        def __init__(self, exc):
            FakeGHL.__init__(self)
            self.exc = exc

        def __call__(self, method, url, headers, body):
            if method == "POST" and url.endswith("/customFields"):
                raise self.exc
            return FakeGHL.__call__(self, method, url, headers, body)

    def test_unexpected_exception_after_creates_exit_1_and_lists_them(self):
        for exc in (RuntimeError("boom " + TOKEN), KeyError("id"), ValueError("bad json"),
                    TypeError("nope")):
            fake = self.RaisesOnFields(exc)
            code, out = self.run_cli(fake, extra=["--apply"])
            self.assertEqual(code, 1, (exc, out))
            self.assertIn("already created before the error: tag 'call-booked', tag 'call-cancelled', "
                          "pipeline 'Call Booked Pipeline'", out)
            self.assertIn("--apply stopped part-way: {}".format(type(exc).__name__), out)
            self.assertIn("rerun to finish", out)
            self.assertNotIn(TOKEN, out)
            # Max-2 re-review, item 2: no answer from GHL, so it may hold it.
            self.assertIn("possibly created: field 'call_time' was in flight; GHL may hold it", out)

    def test_unexpected_exception_on_the_first_create_exit_1(self):
        def raise_on_post(method, url, headers, body):
            if method == "POST":
                raise ValueError("unexpected answer")
            return FakeGHL()(method, url, headers, body)
        code, out = self.run_cli(raise_on_post, extra=["--apply"])
        self.assertEqual(code, 1, out)  # not exit 2: the account was being written
        # Max-2 re-review, item 2: the create got no answer, so GHL may hold it.
        self.assertIn("possibly created: tag 'call-booked' was in flight; GHL may hold it; a dry run "
                      "shows which.", out)
        self.assertNotIn("nothing was created", out)
        self.assertIn("ValueError: unexpected answer", out)


class CtrlCOnCreate(FakeGHL):
    """Ctrl-C lands while create number `at` is in flight (it never answers)."""

    def __init__(self, at):
        FakeGHL.__init__(self)
        self.at = at

    def __call__(self, method, url, headers, body):
        if method == "POST" and len(self.writes()) == self.at - 1:
            raise KeyboardInterrupt()
        return FakeGHL.__call__(self, method, url, headers, body)


class CtrlCOnReread(FakeGHL):
    """Every create succeeds; Ctrl-C lands during the re-read after them."""

    def __call__(self, method, url, headers, body):
        if method == "GET" and self.writes():
            raise KeyboardInterrupt()
        return FakeGHL.__call__(self, method, url, headers, body)


class TestCtrlC(Base):
    """Max-2 should-fix: Ctrl-C after a create lists what was created, exit 1."""

    ALL = ("already created before the error: tag 'call-booked', tag 'call-cancelled', "
           "pipeline 'Call Booked Pipeline', field 'call_time', field 'call_notes', "
           "custom_value 'booking_link'")

    def test_during_the_fourth_create(self):
        fake = CtrlCOnCreate(4)
        code, out = self.run_cli(fake, extra=["--apply"])
        self.assertEqual(code, 1, out)
        self.assertEqual(len(fake.writes()), 3)
        self.assertIn("already created before the error: tag 'call-booked', tag 'call-cancelled', "
                      "pipeline 'Call Booked Pipeline'\n", out)
        self.assertIn("possibly created: field 'call_time' was in flight; GHL may hold it; a dry run "
                      "shows which.", out)
        self.assertIn("error: --apply stopped part-way: interrupted (Ctrl-C)", out)
        self.assertIn("rerun to finish", out)
        self.assertNotIn(TOKEN, out)

    def test_during_the_first_create(self):
        """Max-2 re-review, item 2: whether or not the request reached GHL,
        a create cut off by Ctrl-C is named, never "nothing was created"."""
        code, out = self.run_cli(CtrlCOnCreate(1), extra=["--apply"])
        self.assertEqual(code, 1, out)
        self.assertIn("possibly created: tag 'call-booked' was in flight; GHL may hold it; a dry run "
                      "shows which.", out)
        self.assertNotIn("nothing was created", out)
        self.assertIn("interrupted (Ctrl-C)", out)

    def test_during_the_reread_after_the_creates(self):
        fake = CtrlCOnReread()
        code, out = self.run_cli(fake, extra=["--apply"])
        self.assertEqual(code, 1, out)
        self.assertEqual(len(fake.writes()), 6)
        self.assertIn(self.ALL, out)
        self.assertIn("error after the creates: interrupted (Ctrl-C)", out)

    def test_during_the_id_map_write_after_the_creates(self):
        path = gp.id_map_path(LOC, self.catalog)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write('{"workflow:Old": "W1"}\n')
        with mock.patch.object(gp, "write_json_atomic", side_effect=KeyboardInterrupt()):
            code, out = self.run_cli(FakeGHL(), extra=["--apply"])
        self.assertEqual(code, 1, out)
        self.assertIn(self.ALL, out)
        self.assertIn("error after the creates: interrupted (Ctrl-C)", out)
        with open(path, "r", encoding="utf-8") as fh:
            self.assertEqual(fh.read(), '{"workflow:Old": "W1"}\n')

    def test_between_the_creates_and_the_reread(self):
        """Outside every per-step wrapper: run() still knows what was made."""
        real = gp.apply_plan

        def then_ctrl_c(client, needs, rows, created=None):
            real(client, needs, rows, created)
            raise KeyboardInterrupt()
        fake = FakeGHL()
        with mock.patch.object(gp, "apply_plan", side_effect=then_ctrl_c):
            code, out = self.run_cli(fake, extra=["--apply"])
        self.assertEqual(code, 1, out)
        self.assertEqual(len(fake.writes()), 6)
        self.assertIn(self.ALL, out)
        self.assertIn("interrupted (Ctrl-C)", out)

    def test_before_any_create_it_propagates(self):
        """Nothing was written yet, so Ctrl-C stops the run as usual."""
        calls = []

        def ctrl_c(method, url, headers, body):
            calls.append(method)
            raise KeyboardInterrupt()
        for extra in (["--apply"], []):
            with self.assertRaises(KeyboardInterrupt):
                self.run_cli(ctrl_c, extra=extra)
        self.assertEqual(calls, ["GET", "GET"])
        self.assertFalse(os.path.exists(gp.id_map_path(LOC, self.catalog)))


class TestFieldNameKeys(Base):
    """Round-4 should-fix: two field names GHL would give one key."""

    def test_two_names_with_one_key_exit_2_naming_both(self):
        spec = _spec(
            {"key": "u1", "kind": "app.action", "app": "ghl", "op": "update_contact_field",
             "params": {"field": "Lead-Score", "value": "1"}},
            {"key": "u2", "kind": "app.action", "app": "ghl", "op": "update_contact_field",
             "params": {"field": "Lead Score", "value": "2"}})
        fake = FakeGHL()
        code, out = self.run_cli(fake, spec=spec, extra=["--apply"])
        self.assertEqual(code, 2, out)
        self.assertIn("'Lead-Score' and 'Lead Score'", out)
        self.assertIn("'lead_score'", out)
        self.assertEqual(fake.calls, [])

    def test_one_name_spelled_one_way_still_creates_one_field(self):
        spec = _spec(
            {"key": "u1", "kind": "app.action", "app": "ghl", "op": "update_contact_field",
             "params": {"field": "Lead Score", "value": "1"}},
            {"key": "u2", "kind": "app.action", "app": "ghl", "op": "ai_step",
             "params": {"prompt": "x", "output_field": "Lead Score"}})
        fake = FakeGHL()
        code, out = self.run_cli(fake, spec=spec, extra=["--apply"])
        self.assertEqual(code, 0, out)
        self.assertEqual([d["name"] for _m, p, _h, d in fake.writes() if p.endswith("/customFields")],
                         ["Lead Score"])


class TestUncertainConditionWarning(Base):
    """Round-4 should-fix: say which node's condition gave no tags."""

    SPEC = _spec(
        {"key": "t", "kind": "trigger.app", "app": "ghl", "op": "contact_tag_added",
         "params": {"tag": "call-booked"}},
        {"key": "gate", "kind": "flow.branch", "params": {"condition": 'has tag "hot" but not "cold"'}})

    def test_warning_names_the_node_and_nothing_is_created_for_it(self):
        fake = FakeGHL()
        code, out = self.run_cli(fake, spec=self.SPEC, extra=["--apply"])
        self.assertEqual(code, 0, out)
        self.assertIn("warning: node 'gate': could not tell for certain which tags the If/Else "
                      "condition 'has tag \"hot\" but not \"cold\"' tests", out)
        self.assertEqual([d["name"] for _m, _p, _h, d in fake.writes()], ["call-booked"])
        self.assertNotIn("everything the spec needs exists", out)
        self.assertIn("the tags of the condition(s) warned about above were not checked", out)

    def test_dry_run_warns_too(self):
        code, out = self.run_cli(FakeGHL(), spec=self.SPEC)
        self.assertEqual(code, 1, out)
        self.assertIn("warning: node 'gate'", out)

    def test_no_warning_for_a_certain_condition(self):
        spec = _spec({"key": "gate", "kind": "flow.branch",
                      "params": {"condition": 'contact tag includes "call-booked"'}})
        needs = gp.derive(spec)
        self.assertEqual((needs.tags, needs.warnings), (["call-booked"], []))
        code, out = self.run_cli(FakeGHL(tags=[{"id": "T1", "name": "call-booked"}]), spec=spec)
        self.assertEqual(code, 0, out)
        self.assertNotIn("warning", out)
        self.assertIn("everything the spec needs exists", out)


class TestListTags(Base):
    """Re-review defect 5: params.tag may be a list on tag triggers and If/Else
    gates. add_tag, remove_tag and goal take one tag (compile_ghl's
    name_param_problem: a list compiled to a nested tag list)."""

    ONE_TAG = "`tag` must be one tag name (a string)"

    def test_each_string_in_a_list_is_added(self):
        spec = _spec(
            {"key": "t", "kind": "trigger.app", "app": "ghl", "op": "contact_tag_added",
             "params": {"tag": ["t1", "t2"]}},
            {"key": "g", "kind": "flow.branch", "params": {"tag": ["g1", "g2"], "condition": "has g1 or g2"}},
            {"key": "s", "kind": "app.action", "app": "ghl", "op": "add_tag", "params": {"tag": "plain"}})
        self.assertEqual(gp.derive(spec).tags, ["t1", "t2", "g1", "g2", "plain"])
        fake = FakeGHL()
        code, out = self.run_cli(fake, spec=spec, extra=["--apply"])
        self.assertEqual(code, 0, out)
        self.assertEqual([d["name"] for _m, p, _h, d in fake.writes()], ["t1", "t2", "g1", "g2", "plain"])
        # A list on a tag step or goal is exit 2 before any call.
        for op, tag in (("add_tag", ["a1", "a2"]), ("remove_tag", ["r1"]), ("goal", ["g1", "g2"])):
            fake = FakeGHL()
            code, out = self.run_cli(fake, spec=_spec({"key": "n", "kind": "app.action", "app": "ghl",
                                                       "op": op, "params": {"tag": tag}}), extra=["--apply"])
            self.assertEqual(code, 2, (op, out))
            self.assertIn(self.ONE_TAG, out)
            self.assertEqual(fake.calls, [], op)

    def test_non_string_item_exit_2_before_any_call(self):
        for op, tag, message in (
                ("add_tag", ["ok", 5], self.ONE_TAG), ("remove_tag", [{"name": "x"}], self.ONE_TAG),
                ("contact_tag_added", ["ok", None], "`tag` must be a tag name or a list of tag names"),
                ("goal", [["nested"]], self.ONE_TAG), ("add_tag", 7, self.ONE_TAG)):
            fake = FakeGHL()
            spec = _spec({"key": "n", "kind": "app.action", "app": "ghl", "op": op, "params": {"tag": tag}})
            code, out = self.run_cli(fake, spec=spec, extra=["--apply"])
            self.assertEqual(code, 2, (op, tag, out))
            self.assertIn(message, out)
            self.assertEqual(fake.calls, [], (op, tag))

    # Round-4 review, defect 2: a pipeline, stage or If/Else tag that is not a
    # name must never become an object named after its repr.
    NOT_NAMES = (
        ({"key": "o", "kind": "app.action", "app": "ghl", "op": "create_opportunity",
          "params": {"pipeline": {"name": "Demo", "stages": ["New", "Won"]}, "stage": "New"}},
         "`pipeline` must be a pipeline name"),
        ({"key": "o", "kind": "app.action", "app": "ghl", "op": "update_opportunity",
          "params": {"pipeline": ["Demo"], "stage": "New"}}, "`pipeline` must be a pipeline name"),
        ({"key": "o", "kind": "app.action", "app": "ghl", "op": "create_opportunity",
          "params": {"pipeline": "Demo", "stage": {"name": "New"}}}, "`stage` must be a stage name"),
        ({"key": "o", "kind": "app.action", "app": "ghl", "op": "create_opportunity",
          "params": {"pipeline": "Demo", "stage": 3}}, "`stage` must be a stage name"),
        ({"key": "t", "kind": "trigger.app", "app": "ghl", "op": "pipeline_stage_changed",
          "params": {"pipeline": 7, "stage": "New"}}, "`pipeline` must be a pipeline name"),
        ({"key": "g", "kind": "flow.branch", "params": {"tag": {"name": "vip"}, "condition": "has vip"}},
         "`tag` must be a tag name or a list of tag names"),
        ({"key": "g", "kind": "flow.branch", "params": {"tag": ["vip", 5], "condition": "has vip"}},
         "`tag` must be a tag name or a list of tag names"),
        ({"key": "g", "kind": "flow.branch", "params": {"tag": 0, "condition": "has vip"}},
         "`tag` must be a tag name or a list of tag names"),
        # Max-2 review, defect 2: every other param ghl_prereqs names an object
        # after. These created fields named "{'name': 'Lead Score'}", "5",
        # "True", "{'key': 'summary'}" and "['Summary']" on --apply.
        ({"key": "u", "kind": "app.action", "app": "ghl", "op": "update_contact_field",
          "params": {"field": {"name": "Lead Score"}, "value": "1"}}, "`field` must be a custom field name"),
        ({"key": "u", "kind": "app.action", "app": "ghl", "op": "update_contact_field",
          "params": {"field": 5, "value": "1"}}, "`field` must be a custom field name"),
        ({"key": "u", "kind": "app.action", "app": "ghl", "op": "update_contact_field",
          "params": {"field": True, "value": "1"}}, "`field` must be a custom field name"),
        ({"key": "a", "kind": "app.action", "app": "ghl", "op": "ai_step",
          "params": {"prompt": "x", "output_field": {"key": "summary"}}},
         "`output_field` must be a custom field name"),
        ({"key": "a", "kind": "app.action", "app": "ghl", "op": "ai_step",
          "params": {"prompt": "x", "output_field": ["Summary"]}},
         "`output_field` must be a custom field name"),
        ({"key": "a", "kind": "ai.llm", "params": {"prompt": "x", "output_field": 7}},
         "`output_field` must be a custom field name"),
        # ...the tag of tag steps, tag triggers and goals (compile_ghl emitted it as is)...
        ({"key": "n", "kind": "app.action", "app": "ghl", "op": "add_tag", "params": {"tag": {"name": "vip"}}},
         "`tag` must be one tag name (a string)"),
        ({"key": "n", "kind": "trigger.app", "app": "ghl", "op": "contact_tag_added", "params": {"tag": 5}},
         "`tag` must be a tag name or a list of tag names"),
        ({"key": "n", "kind": "app.action", "app": "ghl", "op": "goal",
          "params": {"goal_type": "tag_added", "tag": [{"name": "x"}]}},
         "`tag` must be one tag name (a string)"),
        # ...and `stages`, which becomes the created pipeline's stage names.
        ({"key": "o", "kind": "app.action", "app": "ghl", "op": "create_opportunity",
          "params": {"pipeline": "Demo", "stage": "New", "stages": "New, Won"}},
         "`stages` must be a list of stage names"),
        ({"key": "o", "kind": "app.action", "app": "ghl", "op": "create_opportunity",
          "params": {"pipeline": "Demo", "stage": "New", "stages": ["New", 5]}},
         "every entry in `stages` must be a stage name"),
    )

    def test_non_string_pipeline_stage_or_branch_tag_exit_2_before_any_call(self):
        for node, message in self.NOT_NAMES:
            with self.assertRaises(gp.ConfigError, msg=node) as ctx:
                gp.derive(_spec(node))
            self.assertIn(message, str(ctx.exception))
            fake = FakeGHL()
            code, out = self.run_cli(fake, spec=_spec(node), extra=["--apply"])
            self.assertEqual(code, 2, (node, out))
            self.assertIn(message, out)
            self.assertIn("node {!r}".format(node["key"]), out)
            self.assertEqual(fake.calls, [], node)

    @staticmethod
    def _mini_spec(node):
        """A one-workflow GHL spec holding `node`, for compile and the prompt."""
        from upwork_gen.spec import WorkflowSpec
        node = dict(node, label="Step", app=node.get("app", "ghl"))
        if node["kind"] == "trigger.app":
            nodes = [node, {"key": "a", "kind": "app.action", "app": "ghl", "op": "send_sms",
                            "label": "Text", "params": {"message": "hi"}}]
            edges = [{"from": node["key"], "to": "a"}]
        else:
            nodes = [{"key": "t", "kind": "trigger.app", "app": "ghl", "op": "contact_tag_added",
                      "label": "Tag x added", "params": {"tag": "x"}}, node]
            edges = [{"from": "t", "to": node["key"]}]
        return WorkflowSpec.from_dict({"title": "Mini", "platform": "gohighlevel",
                                       "nodes": nodes, "edges": edges})

    def test_compile_refuses_the_same_non_string_names(self):
        from upwork_gen.spec import SpecError
        for node, message in self.NOT_NAMES:
            with self.assertRaises(SpecError, msg=node) as ctx:
                compile_ghl.compile_ghl(self._mini_spec(node), {}, "loc")
            self.assertIn(message, str(ctx.exception))
            self.assertIn("node {!r} (Step): ".format(node["key"]), str(ctx.exception))
        # The shared reader refuses on its own too, for any other caller.
        with self.assertRaises(SpecError):
            compile_ghl.condition_tags({"tag": {"name": "vip"}}, "")

    def test_builder_prompt_refuses_the_same_non_string_names(self):
        """Should-fix: render_prompt (run before compile by generate, and alone by
        `upwork_gen ghl`, which copies the prompt to the clipboard) crashed with
        TypeError on a dict pipeline and wrote the other reprs into the prompt.
        It now raises compile_ghl's SpecError, word for word, before any text."""
        from upwork_gen.compile_ghl_prompt import render_prompt
        from upwork_gen.spec import SpecError
        for node, message in self.NOT_NAMES:
            spec = self._mini_spec(node)
            with self.assertRaises(SpecError, msg=node) as prompt_ctx:
                render_prompt(spec)
            with self.assertRaises(SpecError, msg=node) as compile_ctx:
                compile_ghl.compile_ghl(spec, {}, "loc")
            self.assertEqual(str(prompt_ctx.exception), str(compile_ctx.exception), node)
            self.assertIn(message, str(prompt_ctx.exception))

    def test_needs_sinks_refuse_non_strings(self):
        """The two places that used str(value) to make a name refuse instead,
        for any caller that skips name_param_problem."""
        needs = gp.Needs()
        for bad in ({"name": "x"}, 5, True, ["x"], None):
            with self.assertRaises(gp.ConfigError, msg=bad):
                needs.add_field_ref(bad, "node 'u' field")
            with self.assertRaises(gp.ConfigError, msg=bad):
                needs.add_tag(bad)
        self.assertEqual((needs.tags, needs.fields, needs.field_names), ([], [], []))


class TestConditionTagLists(unittest.TestCase):
    """Re-review defect 3: a quoted tag list is taken whole or not at all."""

    WHOLE = (
        ('Has "hot" or "warm" tag', ["hot", "warm"]),
        ('Has tag "a" (or "b")', ["a", "b"]),
        ('tag contains "a" || "b"', ["a", "b"]),
        ('tag contains "a" && "b"', ["a", "b"]),
        ('tag in ["a", "b"]', ["a", "b"]),
        ('tags include both "a" and "b"', ["a", "b"]),
        ('contact tag includes "bid-sent" and opportunity stage is "Won"', ["bid-sent"]),
        ('has "a" tag and stage is "Won"', ["a"]),
        ('tag is "a", \'b\' or "c"', ["a", "b", "c"]),
        ("contact doesn't have tag 'vip'", ["vip"]),
        # A value another subject names is passed over, before or after the tag list.
        ('email contains "@gmail.com" and tag is "a"', ["a"]),
        ('stage is "Won" or "Lost" and tag is "a"', ["a"]),
        ('"Won" stage and has tag "a"', ["a"]),
        ('has tag "a" and status is "open"', ["a"]),
        ('tag includes "hot" and custom field "Lead Type" is "commercial"', ["hot"]),
        ('Contact has the "call-booked" tag', ["call-booked"]),
    )
    UNCERTAIN = (
        'tag is "a" or is "b"',
        'tag score is "high"',
        'has "a" lead tag',
        'has tag "a" and no other tags',
        # Round-4 review, defect 1: any joiner that does not name another subject.
        'has tag "hot" but not "cold"',
        'tags are "a" and also "b"',
        'has tag "a" except "b"',
        'has tag "a" unless "b"',
        'tag is "a" plus "b"',
        'tag is "a" as well as "b"',
        'has tag "a" (but not "b")',
        'tag includes "a"; "b"',
        'tag includes "a" nor "b"',
        'tag is "a" then "b"',
        'tag is "a" maybe "b"',
        'tag is "a" - "b"',
        'has tag "a", not "b"',
        'has tag "a" and not "b"',
        # ...and a value no tag word or subject claims before the tag list.
        'has "vip" or tag is "hot"',
        # Another subject's value only carries over without a clause break.
        'has tag "a" and stage "Won" and also "b"',
        'stage is "Won" and has "vip"',
        # Should-fix: a tag list that also reads as another subject's value.
        'tag is "a" or "Won" stage',
        'has tag "a" with status "open"',
        # Should-fix: typographic or unpaired quotes are never guessed at.
        'tag contains “hot”',
        'tag contains ‘hot’',
        'contact doesn’t have tag "vip"',
        'tag is "a" or "b',
        'tag is \'a\' or \'b',
        'tag is "a" or " "',
        # A tag word no quote belongs to.
        'has the vip tag',
        # Defect 3: must stay unresolved, never become a reply check.
        'has tag "replied" or is "x"',
        # Max-2 review, defect 1: after a tag list, a later value is another
        # subject's only when the text between names it; a noun after the
        # value is not enough (these compiled to index-of-false ["hot-lead"]
        # and the like, the inverse of the intent, or dropped the stage).
        'Contact has tag "hot-lead" and is not in the "Closed" stage',
        'has tag "hot-lead" and is not in "Lost" stage',
        'has tag "a" and has no "Lost" status',
        'tag is "vip" and not "Won" status',
        'has tag "a" without "Lost" stage',
        'has tag "a" or "b" and not "c" stage',
        'Contact has tag "hot-lead" and is in the "Won" stage',
        'has tag "hot-lead" but is not in "Lost" stage',
        '"b" tag and has "a" stage',
        'has tag "a" or "b" tag and "c" stage',
    )

    def _branch(self, **params):
        return _spec({"key": "g", "kind": "flow.branch", "params": params})

    def test_whole_lists(self):
        for cond, tags in self.WHOLE:
            self.assertEqual(compile_ghl.condition_tags({}, cond), tags, cond)
            self.assertEqual(gp.derive(self._branch(condition=cond)).tags, tags, cond)
            self.assertEqual(compile_ghl._tag_condition({"condition": cond})[0], tags, cond)
            conditions, _unresolved = self._compile_branch(cond)
            self.assertEqual([c["conditionValue"] for c in conditions], [tags], cond)

    def test_uncertain_lists_are_none_and_unresolved(self):
        for cond in self.UNCERTAIN:
            self.assertIsNone(compile_ghl.condition_tags({}, cond), cond)
            self.assertIsNone(compile_ghl._tag_condition({"condition": cond}), cond)
            needs = gp.derive(self._branch(condition=cond))
            self.assertEqual(needs.tags, [], cond)
            self.assertEqual(len(needs.warnings), 1, cond)
            # compile: no condition at all (never a subset, never a reply check), and reported.
            conditions, unresolved = self._compile_branch(cond)
            self.assertEqual(conditions, [], cond)
            self.assertEqual(unresolved, ["condition:Check -> " + cond], cond)

    def test_but_not_is_not_compiled_as_its_inverse(self):
        """The round-4 example: this used to compile to index-of-false ["hot"]."""
        conditions, unresolved = self._compile_branch('has tag "hot" but not "cold"')
        self.assertEqual(conditions, [])
        self.assertIn('condition:Check -> has tag "hot" but not "cold"', unresolved)

    def test_stage_clause_after_the_tag_list_is_not_compiled_as_the_tag_test(self):
        """Max-2 review, defect 1: "not in the Closed stage" compiled to "does NOT
        have hot-lead", and "in the Won stage" to a bare tag test that dropped the
        stage. Both are unresolved again, and derive warns instead of guessing."""
        for cond in ('Contact has tag "hot-lead" and is not in the "Closed" stage',
                     'Contact has tag "hot-lead" and is in the "Won" stage'):
            conditions, unresolved = self._compile_branch(cond)
            self.assertEqual(conditions, [], cond)
            self.assertEqual(unresolved, ["condition:Check -> " + cond], cond)
            needs = gp.derive(self._branch(condition=cond))
            self.assertEqual(needs.tags, [], cond)
            self.assertIn("node 'g': could not tell for certain", needs.warnings[0])
        # A value before any tag list may still be named by the noun after it.
        self.assertEqual(compile_ghl.condition_tags({}, '"Won" stage and has tag "a"'), ["a"])

    def test_reply_check_only_when_the_condition_names_no_tags(self):
        """Defect 3: None (tags not pinned down) is unresolved, even with a reply word."""
        for cond, want in (("contact replied", "true"), ("Did the contact reply?", "true"),
                           ("contact did not reply", "false")):
            self.assertEqual(compile_ghl.condition_tags({}, cond), [], cond)
            conditions, unresolved = self._compile_branch(cond)
            self.assertEqual([(c["conditionSubType"], c["conditionValue"]) for c in conditions],
                             [("contact_replied", want)], cond)
            self.assertEqual(unresolved, [], cond)
        for cond in ('has tag "replied" or is "x"', 'contact replied with "yes"', 'has the replied tag'):
            self.assertIsNone(compile_ghl.condition_tags({}, cond), cond)
            conditions, unresolved = self._compile_branch(cond)
            self.assertEqual(conditions, [], cond)
            self.assertEqual(unresolved, ["condition:Check -> " + cond], cond)

    def test_negations(self):
        for cond, tags in (('contact does not have tag "a" or "b"', ["a", "b"]),
                           ('tag != "x"', ["x"]),
                           ("contact doesn't have tag 'vip'", ["vip"]),
                           ('tags exclude "a", "b"', ["a", "b"])):
            self.assertEqual(compile_ghl._tag_condition({"condition": cond}), (tags, True), cond)
        self.assertEqual(compile_ghl._tag_condition({"condition": 'Has "hot" or "warm" tag'}),
                         (["hot", "warm"], False))

    def _compile_branch(self, cond):
        from upwork_gen.spec import WorkflowSpec
        spec = WorkflowSpec.from_dict({"title": "Mini", "platform": "gohighlevel", "nodes": [
            {"key": "t", "kind": "trigger.app", "app": "ghl", "op": "contact_tag_added",
             "label": "Tag x added", "params": {"tag": "x"}},
            {"key": "c", "kind": "flow.branch", "label": "Check", "params": {"condition": cond}},
            {"key": "a", "kind": "app.action", "app": "ghl", "op": "send_sms", "label": "Text",
             "params": {"message": "hi"}}],
            "edges": [{"from": "t", "to": "c"}, {"from": "c", "to": "a", "branch": "true"}]})
        wf, unresolved = compile_ghl.compile_ghl(spec, {}, "loc")
        cond_node = [n for n in wf["nodes"] if n.get("nodeType") == "condition-node"][0]
        return cond_node["attributes"]["branches"][0]["segments"][0]["conditions"], unresolved

    def test_compile_uses_the_whole_list_or_marks_unresolved(self):
        conditions, unresolved = self._compile_branch('Has "hot" or "warm" tag')
        self.assertEqual([c["conditionValue"] for c in conditions], [["hot", "warm"]])
        self.assertFalse([u for u in unresolved if u.startswith("condition:")])
        conditions, unresolved = self._compile_branch('tag is "a" or is "b"')
        self.assertEqual(conditions, [])
        self.assertIn('condition:Check -> tag is "a" or is "b"', unresolved)

    def test_params_tag_wins(self):
        self.assertEqual(compile_ghl.condition_tags({"tag": "vip"}, 'tag is "a" or is "b"'), ["vip"])
        self.assertEqual(compile_ghl.condition_tags({"tag": ["a", "b"]}, ""), ["a", "b"])


def _field_step(key, name, op="update_contact_field"):
    if op == "ai_step":
        return {"key": key, "kind": "ai.llm", "params": {"prompt": "x", "output_field": name}}
    return {"key": key, "kind": "app.action", "app": "ghl", "op": op, "params": {"field": name, "value": "1"}}


class TestLookAlikeFields(Base):
    """Max-2 re-review, item 1: a field is its GHL key. Look-alike matching may
    only refuse or ask for a hand fix, never turn a create into "exists" and
    never drop a spec name."""

    # (GHL field name, spec field name): equal under _norm, different keys.
    LOOK_ALIKES = (
        ("Roof Area (ft\u00b2)", "Roof Area (ft2)"),                     # superscript two
        ("Lead\u200bScore", "LeadScore"),                                 # zero-width space
        ("Score\u00b2", "Score2"),
        ("Tier \u2161", "Tier II"),                                       # Roman numeral two
        ("Step \u2460", "Step 1"),                                        # circled one
        ("\u2116 of Units", "No of Units"),                               # numero sign
        ("Lead Score\u2122", "Lead ScoreTM"),                             # trade mark sign
        ("Unit \u33a1", "Unit m2"),                                       # square m
        ("\uff2c\uff45\uff41\uff44 \uff33\uff43\uff4f\uff52\uff45", "Lead Score"),  # fullwidth
        ("\ufb01le Count", "file Count"),                                 # fi ligature
        ("Stra\u00dfe", "STRASSE"),                                       # sharp s
    )

    def test_ghl_field_that_only_looks_alike_is_a_hand_fix(self):
        for ghl_name, spec_name in self.LOOK_ALIKES:
            self.assertNotEqual(gp._snake(ghl_name), gp._snake(spec_name))
            self.assertEqual(gp._norm(ghl_name), gp._norm(spec_name))
            spec = _spec({"key": "t", "kind": "trigger.app", "app": "ghl", "op": "contact_tag_added",
                          "params": {"tag": "call-booked"}}, _field_step("u", spec_name))
            for extra in (["--apply"], []):
                fake = FakeGHL(fields=[{"id": "F1", "name": ghl_name,
                                        "fieldKey": "contact." + gp._snake(ghl_name)}])
                code, out = self.run_cli(fake, spec=spec, extra=extra)
                case = (ghl_name, spec_name, extra, out)
                self.assertEqual(code, 3, case)
                self.assertIn("NAME MISMATCH", out)
                self.assertIn("action needed: GHL has field {!r}, which differs from the spec's {!r} only "
                              "by case, spacing or look-alike characters (GHL gives it another key): "
                              "rename it in GHL or change the spec so the names match exactly, then "
                              "rerun.".format(ghl_name, spec_name), out)
                self.assertNotIn("everything the spec needs exists", out)
                # Nothing is created for the field; the rest of the spec still is.
                posted = [(p, d["name"]) for _m, p, _h, d in fake.writes()]
                self.assertEqual(posted, [("/locations/{}/tags".format(LOC), "call-booked")] if extra else [],
                                 case)

    def test_case_spacing_key_and_field_key_still_count_as_existing(self):
        """The rules before this round: case and spacing, the same key, or the
        fieldKey. Each is the same GHL field, so nothing is created."""
        for ghl in ({"id": "F1", "name": "lead score"},
                    {"id": "F1", "name": " Lead\u00a0 Score "},
                    {"id": "F1", "name": "Lead-Score"},
                    {"id": "F1", "name": "Score (Lead)", "fieldKey": "contact.lead_score"}):
            fake = FakeGHL(fields=[ghl])
            code, out = self.run_cli(fake, spec=_spec(_field_step("u", "Lead Score")), extra=["--apply"])
            self.assertEqual(code, 0, (ghl, out))
            self.assertEqual(fake.writes(), [], ghl)
            self.assertIn("everything the spec needs exists", out)

    def test_two_spec_spellings_that_only_look_alike_exit_2_naming_both(self):
        for a, b in (("Roof Area (ft\u00b2)", "Roof Area (ft2)"), ("Roof Area (ft2)", "Roof Area (ft\u00b2)"),
                     ("LeadScore", "Lead\u200bScore"), ("Tier II", "Tier \u2161"),
                     ("file Count", "\ufb01le Count")):
            spec = _spec(_field_step("u", a), _field_step("a", b, op="ai_step"))
            needs = gp.derive(spec)
            self.assertEqual(needs.field_names, [a, b])  # neither name is dropped
            with self.assertRaises(gp.ConfigError):
                gp.validate(needs)
            # check_spec_names still refuses the pair on its own...
            with self.assertRaises(gp.ConfigError) as ctx:
                gp.check_spec_names(needs)
            self.assertIn("the spec spells one field {!r} and {!r}: they differ only by case, spacing or "
                          "look-alike characters, but GHL gives them different keys".format(a, b),
                          str(ctx.exception))
            # ...but the plain-ASCII check runs first (max-3 re-review, item 2).
            odd = a if any(ord(c) > 126 for c in a) else b
            fake = FakeGHL()
            code, out = self.run_cli(fake, spec=spec, extra=["--apply"])
            self.assertEqual(code, 2, (a, b, out))
            self.assertIn("field {}".format(ascii(odd)), out)
            self.assertIn("GHL names in a spec must be plain ASCII", out)
            self.assertEqual(fake.calls, [], (a, b))

    def test_case_and_spacing_respellings_are_still_one_field(self):
        spec = _spec(_field_step("u", "Lead Score"), _field_step("a", "lead  score", op="ai_step"))
        self.assertEqual(gp.derive(spec).field_names, ["Lead Score"])
        fake = FakeGHL()
        code, out = self.run_cli(fake, spec=spec, extra=["--apply"])
        self.assertEqual(code, 0, out)
        self.assertEqual([d["name"] for _m, _p, _h, d in fake.writes()], ["Lead Score"])


class AnswerLost(FakeGHL):
    """GHL makes create number `at`, then its answer never arrives: `exc`
    (Ctrl-C, a timeout) is raised instead."""

    def __init__(self, at, exc):
        FakeGHL.__init__(self)
        self.at = at
        self.exc = exc

    def __call__(self, method, url, headers, body):
        answer = FakeGHL.__call__(self, method, url, headers, body)
        if method == "POST" and len(self.writes()) == self.at:
            raise self.exc
        return answer


class TestCreateInFlight(Base):
    """Max-2 re-review, item 2: a create that got no answer from GHL is named
    as possibly created, and "nothing was created" is never printed then."""

    IN_FLIGHT = "possibly created: {} was in flight; GHL may hold it; a dry run shows which.\n"

    def test_ctrl_c_after_ghl_made_the_first_create(self):
        fake = AnswerLost(1, KeyboardInterrupt())
        code, out = self.run_cli(fake, extra=["--apply"])
        self.assertEqual(code, 1, out)
        self.assertEqual([t["name"] for t in fake.tags], ["call-booked"])  # GHL holds it
        self.assertIn(self.IN_FLIGHT.format("tag 'call-booked'"), out)
        self.assertNotIn("nothing was created", out)
        self.assertNotIn("already created", out)
        self.assertIn("error: --apply stopped part-way: interrupted (Ctrl-C)", out)
        # ...and the dry run the message points to does show it.
        code, out = self.run_cli(fake)
        self.assertRegex(out, r"(?m)^tag +call-booked +exists$")

    def test_ctrl_c_after_ghl_made_a_later_create(self):
        fake = AnswerLost(3, KeyboardInterrupt())
        code, out = self.run_cli(fake, extra=["--apply"])
        self.assertEqual(code, 1, out)
        self.assertEqual([p["name"] for p in fake.pipelines], ["Call Booked Pipeline"])
        created = "already created before the error: tag 'call-booked', tag 'call-cancelled'\n"
        in_flight = self.IN_FLIGHT.format("pipeline 'Call Booked Pipeline'")
        self.assertIn(created, out)
        self.assertIn(in_flight, out)
        self.assertLess(out.index(in_flight), out.index("error: --apply stopped part-way"))

    def test_timeout_after_ghl_made_the_create(self):
        for at, named, before in (
                (1, "tag 'call-booked'", None),
                (4, "field 'call_time'", "tag 'call-booked', tag 'call-cancelled', pipeline 'Call Booked Pipeline'")):
            fake = AnswerLost(at, socket.timeout("timed out"))
            code, out = self.run_cli(fake, extra=["--apply"])
            self.assertEqual(code, 1, out)
            self.assertEqual(len(fake.writes()), at)
            self.assertIn(self.IN_FLIGHT.format(named), out)
            self.assertIn("network error: timed out", out)
            self.assertNotIn("nothing was created", out)
            self.assertNotIn(TOKEN, out)
            if before:
                self.assertIn("already created before the error: " + before + "\n", out)

    def test_an_http_error_status_is_not_in_flight(self):
        class RefusesThird(FakeGHL):
            def __call__(self, method, url, headers, body):
                if method == "POST" and len(self.writes()) == 2:
                    self.calls.append((method, url[len(gp.BASE_URL):], dict(headers), None))
                    return 422, {"message": "refused"}
                return FakeGHL.__call__(self, method, url, headers, body)
        code, out = self.run_cli(RefusesThird(), extra=["--apply"])
        self.assertEqual(code, 1, out)
        self.assertIn("already created before the error: tag 'call-booked', tag 'call-cancelled'\n", out)
        self.assertIn("HTTP 422", out)
        self.assertNotIn("possibly created", out)
        self.assertNotIn("in flight", out)


class TestTokenCharacters(Base):
    """Max-2 re-review, item 3: a token with whitespace or a control character
    inside it is refused before any call, and no part of it is printed (sent
    as a header, the HTTP library quoted it whole in its error)."""

    LEFT, RIGHT = "pit-SECRET-left-4417", "right-SECRET-9083"
    INSIDE = ("\n", "\r", "\r\n", "\n ", "\t", " ", "\x00", "\x1b", "\x7f", "\x85", "\u00a0", "\u2028",
              "\u3000")

    def test_refused_before_any_call_without_echoing_it(self):
        for inside in self.INSIDE:
            token = self.LEFT + inside + self.RIGHT
            fake = FakeGHL()
            code, out = self.run_cli(fake, extra=["--apply"],
                                     environ={"GHL_PIT_TOKEN": token, "GHL_LOCATION_ID": LOC})
            self.assertEqual(code, 2, (inside, out))
            self.assertEqual(fake.calls, [], repr(inside))
            self.assertIn("error: GHL_PIT_TOKEN has whitespace or a control character inside it", out)
            self.assertNotIn("SECRET", out, repr(inside))
            self.assertEqual(len(out.strip().splitlines()), 1)
            with self.assertRaises(gp.ConfigError) as ctx:
                gp.load_credentials(None, self.env_path, {"GHL_PIT_TOKEN": token})
            self.assertNotIn("SECRET", str(ctx.exception))

    def test_from_the_env_file_too(self):
        with open(self.env_path, "w") as fh:
            fh.write("GHL_PIT_TOKEN={}\t{}\n".format(self.LEFT, self.RIGHT))
        fake = FakeGHL()
        code, out = self.run_cli(fake, environ={})
        self.assertEqual(code, 2, out)
        self.assertEqual(fake.calls, [])
        self.assertNotIn("SECRET", out)

    def test_whitespace_around_the_token_is_still_stripped(self):
        fake = full_account()
        code, out = self.run_cli(fake, environ={"GHL_PIT_TOKEN": "  " + TOKEN + "\n", "GHL_LOCATION_ID": LOC})
        self.assertEqual(code, 0, out)
        self.assertEqual(fake.calls[0][2]["Authorization"], "Bearer " + TOKEN)


class StatusOnCreate(FakeGHL):
    """Create number `at` is answered with HTTP `status`. With `saved`, GHL
    made the object first (a gateway error after the backend wrote it)."""

    def __init__(self, at, status, saved=False):
        FakeGHL.__init__(self)
        self.at = at
        self.status = status
        self.saved = saved
        self.posts = 0

    def __call__(self, method, url, headers, body):
        if method == "POST":
            self.posts += 1
            if self.posts == self.at:
                if self.saved:
                    FakeGHL.__call__(self, method, url, headers, body)
                else:
                    self.calls.append((method, url[len(gp.BASE_URL):], dict(headers),
                                       json.loads(body.decode("utf-8"))))
                return self.status, {"message": "upstream error"}
        return FakeGHL.__call__(self, method, url, headers, body)


class TestGatewayErrorOnCreate(Base):
    """Max-3 re-review, item 1: a 5xx answer to a create can come from a
    gateway after GHL saved the object, so the create is named as possibly
    created and "nothing was created" is never printed. A 4xx is still GHL
    refusing it (TestCreateInFlight.test_an_http_error_status_is_not_in_flight)."""

    STATUSES = (500, 502, 503, 504)
    IN_FLIGHT = "possibly created: {} was in flight; GHL may hold it; a dry run shows which.\n"

    def test_5xx_on_the_first_create(self):
        in_flight = self.IN_FLIGHT.format("tag 'call-booked'")
        for status in self.STATUSES:
            for saved in (True, False):
                fake = StatusOnCreate(1, status, saved)
                code, out = self.run_cli(fake, extra=["--apply"])
                case = (status, saved, out)
                self.assertEqual(code, 1, case)
                self.assertEqual(len(fake.writes()), 1, case)
                error = "error: --apply stopped part-way: POST /locations/{}/tags -> HTTP {}".format(LOC, status)
                self.assertIn(in_flight, out, case)
                self.assertIn(error, out, case)
                self.assertLess(out.index(in_flight), out.index(error), case)
                self.assertNotIn("nothing was created", out, case)
                self.assertNotIn("already created", out, case)
                self.assertNotIn(TOKEN, out, case)
                # The dry run the message points to shows whether GHL holds it.
                code, out = self.run_cli(fake)
                self.assertRegex(out, r"(?m)^tag +call-booked +{}$".format(
                    "exists" if saved else "will create"), case)

    def test_5xx_on_a_later_create_lists_the_earlier_ones(self):
        created = ("already created before the error: tag 'call-booked', tag 'call-cancelled', "
                   "pipeline 'Call Booked Pipeline'\n")
        in_flight = self.IN_FLIGHT.format("field 'call_time'")
        for status in self.STATUSES:
            fake = StatusOnCreate(4, status)
            code, out = self.run_cli(fake, extra=["--apply"])
            case = (status, out)
            self.assertEqual(code, 1, case)
            self.assertEqual(len(fake.writes()), 4, case)
            self.assertIn(created, out, case)
            self.assertIn(in_flight, out, case)
            self.assertLess(out.index(created), out.index(in_flight), case)
            self.assertLess(out.index(in_flight), out.index("error: --apply stopped part-way"), case)
            self.assertIn("POST /locations/{}/customFields -> HTTP {}".format(LOC, status), out, case)
            self.assertNotIn("nothing was created", out, case)


class TestSpecNamesArePlainAscii(Base):
    """Max-3 re-review, defect 2, by Lorenzo's rule: every name the spec asks
    for (tag, custom field name or key, custom value key, pipeline, stage)
    must be plain printable ASCII. "Score" + U+00B2 was created beside
    "Score2" or {{contact.score2}}, which no look-alike check compared it
    with. Such a spec is exit 2 before any call, naming the name with its
    characters escaped. Names already in GHL are not restricted (see
    TestLookAlikeFields and TestExactNames)."""

    RULE = "GHL names in a spec must be plain ASCII"

    @staticmethod
    def _step(key, op, **params):
        return {"key": key, "kind": "app.action", "app": "ghl", "op": op, "params": params}

    def _sms(self, message):
        return self._step("s", "send_sms", message=message)

    def assert_refused(self, spec, named):
        fake = FakeGHL()
        code, out = self.run_cli(fake, spec=spec, extra=["--apply"])
        self.assertEqual(code, 2, (named, out))
        self.assertEqual(fake.calls, [], (named, out))
        self.assertIn(named + ": " + self.RULE, out)
        self.assertFalse(os.path.exists(gp.id_map_path(LOC, self.catalog)))
        return out

    def test_the_three_review_repros_exit_2(self):
        self.assert_refused(
            _spec(_field_step("a", "Score2"), _field_step("b", "Score\u00b2", op="ai_step"),
                  self._sms("You scored {{contact.score2}}")),
            "field 'Score\\xb2' (node 'b' output_field)")
        self.assert_refused(_spec(_field_step("a", "score2"), _field_step("b", "Score\u00b2")),
                            "field 'Score\\xb2' (node 'b' field)")
        self.assert_refused(
            _spec(_field_step("ai", "Roof Area ft\u00b2", op="ai_step"),
                  self._sms("about {{contact.roof_area_ft2}} sq ft")),
            "field 'Roof Area ft\\xb2' (node 'ai' output_field)")

    def test_every_kind_of_name_is_checked(self):
        cases = (
            (self._step("n", "add_tag", tag="vip\u00b2"), "tag 'vip\\xb2' (node 'n')"),
            (self._step("n", "remove_tag", tag="c\u00e1ncelled"), "tag 'c\\xe1ncelled' (node 'n')"),
            ({"key": "t", "kind": "trigger.app", "app": "ghl", "op": "contact_tag_added",
              "params": {"tag": ["ok", "hot\u200b"]}}, "tag 'hot\\u200b' (node 't')"),
            (self._step("g", "goal", goal_type="tag_added", tag="w\u00f6n"), "tag 'w\\xf6n' (node 'g')"),
            ({"key": "c", "kind": "flow.branch", "params": {"condition": 'contact tag includes "b\u00efd"'}},
             "tag 'b\\xefd' (node 'c')"),
            (_field_step("u", "Lead\tScore"), "field 'Lead\\tScore' (node 'u' field)"),
            (_field_step("a", "\uff2c\uff45\uff41\uff44", op="ai_step"),
             "field '\\uff2c\\uff45\\uff41\\uff44' (node 'a' output_field)"),
            (self._sms("at {{contact.sc\u00f6re}}"), "field key 'sc\\xf6re' (node 's' {{contact.sc\\xf6re}})"),
            (_field_step("u", "contact.sc\u00f6re"), "field key 'sc\\xf6re' (node 'u' field)"),
            (self._sms("{{custom_values.b\u00f6oking_link}}"),
             "custom value key 'b\\xf6oking_link' (node 's' {{custom_values.b\\xf6oking_link}})"),
            (self._step("o", "create_opportunity", pipeline="Demo\u00a0Pipe", stage="New"),
             "pipeline 'Demo\\xa0Pipe' (node 'o')"),
            (self._step("o", "create_opportunity", pipeline="Demo", stage="Wo\u0301n"),
             "stage 'Wo\\u0301n' (node 'o')"),
            (self._step("o", "update_opportunity", pipeline="Demo", stage="New", stages=["New", "Won\x7f"]),
             "stage 'Won\\x7f' (node 'o')"),
        )
        for node, named in cases:
            self.assert_refused(_spec(node), named)

    def test_names_a_merge_would_hide_are_still_checked(self):
        """Noted as derive collects them, before any dedupe or drop: the
        Kelvin sign (U+212A) lowercases to "k", "Scor" + U+00E9 snakes to the
        key "scor", and "Email" + U+00B2 to the standard field "email"."""
        cases = (
            (_spec(self._step("a", "add_tag", tag="k"), self._step("b", "add_tag", tag="\u212a")),
             "tag '\\u212a' (node 'b')"),
            (_spec(_field_step("a", "Ka"), _field_step("b", "\u212aa", op="ai_step")),
             "field '\\u212aa' (node 'b' output_field)"),
            (_spec(_field_step("u", "Scor\u00e9"), self._sms("{{contact.scor}}")),
             "field 'Scor\\xe9' (node 'u' field)"),
            (_spec(_field_step("u", "Email\u00b2")), "field 'Email\\xb2' (node 'u' field)"),
        )
        for spec, named in cases:
            self.assert_refused(spec, named)

    def test_every_offending_name_is_listed_once(self):
        spec = _spec(self._step("a", "add_tag", tag="vip\u00b2"), self._step("b", "add_tag", tag="vip\u00b2"),
                     _field_step("u", "Score\u00b2"))
        out = self.assert_refused(spec, "tag 'vip\\xb2' (node 'a')")
        self.assertIn("field 'Score\\xb2' (node 'u' field): " + self.RULE, out)
        self.assertEqual(out.count(self.RULE), 2)


OTHER_LOC = "otherLOC99999"


def _named_field_spec():
    """The Cal.com spec plus a field named by display name, so one --apply
    makes every kind of create this tool has (tag, pipeline, field by key,
    field by name, custom value)."""
    spec = json.loads(json.dumps(calcom_spec()))
    spec["nodes"].append(_field_step("lead_score", "Lead Score"))
    return spec


class Recorder(object):
    """A transport that records every call and answers 200 {}."""

    def __init__(self):
        self.calls = []

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, dict(headers), body))
        return 200, {}


class TestEndpointAllowlist(Base):
    """Least privilege, item 1: only the calls this tool makes ever go out,
    whatever scopes the token carries; anything else is refused before any
    network I/O, without the token in the message."""

    def test_the_allowlist_is_exactly_the_tools_call_sites(self):
        loc = "/locations/" + LOC
        self.assertEqual(gp.allowed_requests(LOC), frozenset([
            ("GET", "/opportunities/pipelines?locationId=" + LOC),
            ("GET", loc + "/tags"),
            ("GET", loc + "/customFields?model=contact"),
            ("GET", loc + "/customValues"),
            ("POST", loc + "/tags"),
            ("POST", loc + "/customFields"),
            ("POST", loc + "/customValues"),
            ("POST", "/opportunities/pipelines"),
        ]))

    def test_every_call_the_tool_makes_still_passes(self):
        for location in (LOC, "A1b2C3d4E5", "Z" * 40, gp.DEFAULT_LOCATION):
            fake = FakeGHL()
            spec = _named_field_spec()
            extra = ["--location", location]
            self.assertEqual(self.run_cli(fake, spec, extra)[0], 1)                  # dry run
            code, out = self.run_cli(fake, spec, extra + ["--apply"])
            self.assertEqual(code, 0, out)
            self.assertEqual(self.run_cli(fake, spec, extra)[0], 0)                  # dry run again
            self.assertNotIn("refused before sending", out)
            sent = set((c[0], c[1]) for c in fake.calls)
            # Every call went out, and together they use the whole allowlist.
            self.assertEqual(sent, gp.allowed_requests(location), location)
            for method, path, headers, body in fake.calls:
                if path == "/opportunities/pipelines":
                    self.assertEqual(body["locationId"], location)
            self.assertEqual([c[1] for c in fake.writes()].count("/opportunities/pipelines"), 1)

    def assert_refused(self, method, path, body=None, reason=None, location=LOC):
        rec = Recorder()
        client = gp.GHLClient(TOKEN, location, rec)
        case = (method, path, body)
        with self.assertRaises(gp.RequestRefused, msg=repr(case)) as ctx:
            client.request(method, path, body)
        self.assertEqual(rec.calls, [], case)
        text = str(ctx.exception)
        self.assertIn("refused before sending", text, case)
        self.assertIn("nothing was sent", text, case)
        self.assertNotIn(TOKEN, text, case)
        self.assertNotIn("SECRET", text, case)
        self.assertIsInstance(ctx.exception, gp.GHLError)
        if reason:
            self.assertIn(reason, text, case)
        return text

    def test_other_methods_are_refused(self):
        for method in ("PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "TRACE", "CONNECT", "get", "post", ""):
            for path in ("/locations/{}/tags".format(LOC), "/opportunities/pipelines",
                         "/locations/{}/customFields".format(LOC)):
                self.assert_refused(method, path, {"name": "x", "locationId": LOC},
                                    "is never used by this tool")

    def test_other_paths_and_queries_are_refused(self):
        L = LOC
        cases = [
            ("GET", "/locations/{}".format(L)),
            ("GET", "/locations/{}/tags/T1".format(L)),
            ("POST", "/locations/{}/tags/T1".format(L)),
            ("GET", "/locations/{}/tags/".format(L)),
            ("GET", "/locations/{}/customFields".format(L)),                  # no model
            ("GET", "/locations/{}/customFields?model=opportunity".format(L)),
            ("GET", "/locations/{}/customFields?model=contact&model=all".format(L)),
            ("POST", "/locations/{}/customFields?model=contact".format(L)),
            ("GET", "/locations/{}/customFields/F1".format(L)),
            ("GET", "/locations/{}/customValues/V1".format(L)),
            ("GET", "/locations/{}/tags?limit=100".format(L)),                # no read pages
            ("GET", "/locations/{}/tags?".format(L)),
            ("GET", "/opportunities/pipelines"),                             # no locationId
            ("GET", "/opportunities/pipelines?locationId={}&limit=5".format(L)),
            ("POST", "/opportunities/pipelines?locationId={}".format(L)),
            ("GET", "/opportunities/pipelines/P1"),
            ("GET", "/contacts/"),
            ("POST", "/contacts/"),
            ("GET", "/users/"),
            ("GET", "/locations/{}/templates".format(L)),
            ("GET", "/oauth/locationToken"),
            ("GET", ""),
            ("GET", "/"),
        ]
        for method, path in cases:
            self.assert_refused(method, path, {"name": "x", "locationId": L}
                                if path.startswith("/opportunities") else None)

    def test_another_location_id_is_refused(self):
        L = LOC
        cases = [
            ("GET", "/locations/{}/tags".format(OTHER_LOC), None),
            ("POST", "/locations/{}/tags".format(OTHER_LOC), {"name": "x"}),
            ("GET", "/locations/{}/customFields?model=contact".format(OTHER_LOC), None),
            ("POST", "/locations/{}/customValues".format(OTHER_LOC), {"name": "x"}),
            ("GET", "/opportunities/pipelines?locationId={}".format(OTHER_LOC), None),
            ("GET", "/opportunities/pipelines?locationId={}&locationId={}".format(L, OTHER_LOC), None),
            ("GET", "/opportunities/pipelines?locationId={}&locationId={}".format(OTHER_LOC, L), None),
            ("GET", "/locations/{}x/tags".format(L), None),
            ("GET", "/locations/{}/tags".format(L.lower()), None),
        ]
        for method, path, body in cases:
            self.assert_refused(method, path, body, "another location id")
        # A pipeline create names its location in the body.
        for body in ({"name": "P", "locationId": OTHER_LOC, "stages": []}, {"name": "P", "stages": []},
                     {"name": "P", "locationId": L.upper(), "stages": []}, None):
            self.assert_refused("POST", "/opportunities/pipelines", body,
                                "the pipeline is not for the configured location id")

    def test_path_tricks_are_refused(self):
        L = LOC
        cases = [
            ("/locations/{}/../{}/tags".format(L, L), "`..`"),
            ("/locations/{}/tags/..".format(L), "`..`"),
            ("/locations/../locations/{}/tags".format(L), "`..`"),
            ("/locations/{}//tags".format(L), "`//`"),
            ("//locations/{}/tags".format(L), "`//`"),
            ("//evil.example.com/locations/{}/tags".format(L), "`//`"),
            ("/locations/{}/tags#frag".format(L), "fragment"),
            ("/locations/{}/tags#".format(L), "fragment"),
            ("/opportunities/pipelines?locationId={}#x".format(L), "fragment"),
            ("/locations/{}%2Ftags".format(L), "percent-encoded"),
            ("/locations/{}%2ftags".format(L), "percent-encoded"),
            ("/locations/{}/tags%2F..%2F".format(L), "percent-encoded"),
            ("/locations/%2e%2e/{}/tags".format(L), "percent-encoded"),
            ("/locations/{}/tags%00".format(L), "percent-encoded"),
            ("/locations/{}\\tags".format(L), "backslash"),
            ("/locations/{}/tags\r\nX-Evil: 1".format(L), "control character"),
            ("/locations/{}/tags\n".format(L), "control character"),
            ("/locations/{}/tags ".format(L), "space"),
            ("/locations/{}/tаgs".format(L), "outside plain ASCII"),
            ("/locations/{}/./tags".format(L), "not an endpoint"),
        ]
        for path, reason in cases:
            for method in ("GET", "POST"):
                self.assert_refused(method, path, {"name": "x"}, reason)

    def test_another_host_is_refused(self):
        L = LOC
        # A path that does not start with "/" would change the host.
        for path in ("@evil.example.com/locations/{}/tags".format(L),
                     ".evil.example.com/locations/{}/tags".format(L),
                     ":8443/locations/{}/tags".format(L),
                     "?/locations/{}/tags".format(L),
                     "#/locations/{}/tags".format(L),
                     "locations/{}/tags".format(L)):
            self.assert_refused("GET", path, None, "the host is not services.leadconnectorhq.com")
        for base in ("https://evil.example.com", "https://services.leadconnectorhq.com.evil.example.com",
                     "https://user@services.leadconnectorhq.com", "https://services.leadconnectorhq.com:8443",
                     "https://SERVICES.leadconnectorhq.com", "https://leadconnectorhq.com",
                     "https://services.leadconnectorhq.com@evil.example.com"):
            with mock.patch.object(gp, "BASE_URL", base):
                self.assert_refused("GET", "/locations/{}/tags".format(L), None,
                                    "the host is not services.leadconnectorhq.com")
        for base in ("http://services.leadconnectorhq.com", "HTTPS://services.leadconnectorhq.com",
                     "ftp://services.leadconnectorhq.com", "//services.leadconnectorhq.com"):
            with mock.patch.object(gp, "BASE_URL", base):
                self.assert_refused("GET", "/locations/{}/tags".format(L), None, "not HTTPS")
        with mock.patch.object(gp, "BASE_URL", "https://services.leadconnectorhq.com/v2"):
            self.assert_refused("GET", "/locations/{}/tags".format(L), None, "not an endpoint")

    def test_a_token_in_a_refused_path_is_redacted(self):
        text = self.assert_refused("GET", "/locations/{}/tags?t={}".format(LOC, TOKEN))
        self.assertIn("<GHL_PIT_TOKEN>", text)
        long_path = "/x/" + "y" * (gp.DETAIL_LIMIT - 30) + TOKEN
        text = self.assert_refused("GET", long_path)
        self.assertNotIn(TOKEN[:10], text)

    def test_a_refused_create_is_not_named_as_possibly_created(self):
        """Nothing was sent, so GHL cannot hold it: the objects made before
        are listed, the refused one is not in flight."""
        real = gp.allowed_requests

        def without_field_create(location):
            return real(location) - {("POST", "/locations/{}/customFields".format(location))}

        fake = FakeGHL()
        with mock.patch.object(gp, "allowed_requests", without_field_create):
            code, out = self.run_cli(fake, extra=["--apply"])
        self.assertEqual(code, 1, out)
        self.assertEqual([c[1] for c in fake.writes()],
                         ["/locations/{}/tags".format(LOC)] * 2 + ["/opportunities/pipelines"])
        self.assertIn("already created before the error: tag 'call-booked', tag 'call-cancelled', "
                      "pipeline 'Call Booked Pipeline'\n", out)
        self.assertIn("error: --apply stopped part-way: POST {}/locations/{}/customFields refused "
                      "before sending: not an endpoint this tool uses".format(gp.BASE_URL, LOC), out)
        self.assertNotIn("possibly created", out)
        self.assertNotIn(TOKEN, out)

    def test_a_refused_read_exits_1_without_any_call(self):
        rec = Recorder()
        with mock.patch.object(gp, "allowed_requests", lambda location: frozenset()):
            code, out = self.run_cli(rec, extra=["--apply"])
        self.assertEqual(code, 1, out)
        self.assertEqual(rec.calls, [])
        self.assertIn("refused before sending", out)
        self.assertNotIn(TOKEN, out)


class TestHttpsHostAndLocation(Base):
    """Least privilege, item 3: HTTPS to services.leadconnectorhq.com only,
    and a location id of 10-40 letters and digits, else exit 2 with no call."""

    def test_base_url_is_https_to_the_api_host(self):
        self.assertEqual(gp.BASE_URL, "https://services.leadconnectorhq.com")
        self.assertEqual(gp.API_HOST, "services.leadconnectorhq.com")
        gp.check_base_url()

    def test_another_base_url_exit_2_before_any_call(self):
        for base in ("http://services.leadconnectorhq.com", "https://evil.example.com",
                     "https://services.leadconnectorhq.com/", "https://services.leadconnectorhq.com:443",
                     "https://services.leadconnectorhq.com.evil.example.com",
                     "https://user:{}@services.leadconnectorhq.com".format(TOKEN), ""):
            fake = FakeGHL()
            with mock.patch.object(gp, "BASE_URL", base):
                code, out = self.run_cli(fake, extra=["--apply"])
            self.assertEqual(code, 2, (base, out))
            self.assertEqual(fake.calls, [], base)
            self.assertIn("error: BASE_URL must be https://services.leadconnectorhq.com", out)
            self.assertNotIn(TOKEN, out)
            self.assertEqual(len(out.strip().splitlines()), 1, out)

    BAD_LOCATIONS = ("short", "abc123456", "a" * 41, "loc-TEST-123", "loc_TEST_123", "loc TEST 123",
                     "locTEST123/../x", "locTEST123/tags", "locTEST123%2F", "locTEST123?x=1",
                     "locTEST123#x", "locTEST123\nx", "ｌｏｃTEST1234", "locTEST12٣",
                     "pit-SECRET-token-looking-value-12345")

    def test_bad_location_id_exit_2_before_any_call_without_echoing_it(self):
        for bad in self.BAD_LOCATIONS:
            for how in ("env", "flag", "file"):
                fake = FakeGHL()
                environ = {"GHL_PIT_TOKEN": TOKEN}
                extra = ["--apply"]
                if how == "env":
                    environ["GHL_LOCATION_ID"] = bad
                elif how == "flag":
                    extra += ["--location", bad]
                else:
                    if "\n" in bad:
                        continue
                    with open(self.env_path, "w", encoding="utf-8") as fh:
                        fh.write("GHL_LOCATION_ID={}\n".format(bad))
                    os.chmod(self.env_path, 0o600)
                case = (bad, how)
                code, out = self.run_cli(fake, extra=extra, environ=environ)
                if os.path.exists(self.env_path):
                    os.unlink(self.env_path)
                self.assertEqual(code, 2, (case, out))
                self.assertEqual(fake.calls, [], case)
                self.assertIn("error: the GHL location id (--location, GHL_LOCATION_ID) is not a location id",
                              out, case)
                self.assertNotIn("SECRET", out, case)
                self.assertNotIn(TOKEN, out, case)
                self.assertEqual(len(out.strip().splitlines()), 1, (case, out))
                self.assertEqual(os.listdir(self.catalog), [], case)

    def test_the_client_refuses_a_bad_location_too(self):
        for bad in self.BAD_LOCATIONS + (None, 12345678901):
            with self.assertRaises(gp.ConfigError):
                gp.GHLClient(TOKEN, bad, Recorder())

    def test_good_location_ids_still_run(self):
        for good in ("A1b2C3d4E5", "Z" * 40, gp.DEFAULT_LOCATION, LOC, "  " + LOC + " "):
            fake = full_account()
            code, out = self.run_cli(fake, environ={"GHL_PIT_TOKEN": TOKEN, "GHL_LOCATION_ID": good})
            self.assertEqual(code, 0, (good, out))
            self.assertTrue(fake.calls)
            self.assertIn("/locations/{}/tags".format(good.strip()), [c[1] for c in fake.calls])


class RedirectOnPost(FakeGHL):
    """POST number `at` is answered with redirect `status` to another
    address. With `saved`, GHL made the object first."""

    def __init__(self, at, status, saved=False):
        FakeGHL.__init__(self)
        self.at = at
        self.status = status
        self.saved = saved
        self.posts = 0

    def __call__(self, method, url, headers, body):
        if method == "POST":
            self.posts += 1
            if self.posts == self.at:
                if self.saved:
                    FakeGHL.__call__(self, method, url, headers, body)
                else:
                    self.calls.append((method, url[len(gp.BASE_URL):], dict(headers),
                                       json.loads(body.decode("utf-8"))))
                return self.status, {"Location": "http://evil.example.com/steal"}
        return FakeGHL.__call__(self, method, url, headers, body)


def _raw_answer(status, body=b"", headers=()):
    lines = ["HTTP/1.1 {} Answer".format(status)] + ["{}: {}".format(k, v) for k, v in headers]
    lines += ["Content-Length: {}".format(len(body)), "", ""]
    return "\r\n".join(lines).encode("ascii") + body


class _FakeSock(object):
    def __init__(self, raw):
        self.raw = raw

    def makefile(self, *args, **kwargs):
        return io.BytesIO(self.raw)

    def close(self):
        pass


_REAL_HTTP_CONNECTION = http.client.HTTPConnection


class FakeWire(object):
    """Stands in for http.client's connections, so urllib's real stack
    (opener, redirect handler, header handling) runs with no socket.
    `answer(scheme, host, method, selector, headers, body)` gives raw bytes."""

    def __init__(self, answer):
        self.answer = answer
        self.sent = []

    def _conn(self, scheme):
        wire = self

        class Conn(object):
            # urllib asks the connection class for a body's length.
            _get_content_length = staticmethod(_REAL_HTTP_CONNECTION._get_content_length)

            def __init__(self, host, timeout=None, **kwargs):
                self.host = host
                self.sock = None
                self.req = None

            def set_debuglevel(self, level):
                pass

            def set_tunnel(self, host, port=None, headers=None):
                raise AssertionError("no proxy expected")

            def request(self, method, url, body=None, headers=None, encode_chunked=False):
                self.req = (scheme, self.host, method, url, dict(headers or {}), body)
                wire.sent.append(self.req)

            def getresponse(self):
                resp = http.client.HTTPResponse(_FakeSock(wire.answer(*self.req)), method=self.req[2])
                resp.begin()
                return resp

            def close(self):
                pass
        return Conn

    def __enter__(self):
        self._patches = [
            mock.patch.object(http.client, "HTTPSConnection", self._conn("https")),
            mock.patch.object(http.client, "HTTPConnection", self._conn("http")),
            mock.patch("urllib.request.getproxies", lambda: {}),
            mock.patch("socket.create_connection", side_effect=AssertionError("network attempted")),
        ]
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in reversed(self._patches):
            p.stop()
        return False


def _account_reads(selector):
    for part, key in (("/opportunities/pipelines", "pipelines"), ("/tags", "tags"),
                      ("/customFields", "customFields"), ("/customValues", "customValues")):
        if part in selector:
            return {key: []}
    return {}


class TestRedirectsAreNeverFollowed(Base):
    """Least privilege, item 2: a redirect is never followed with the token
    (urllib would forward the Authorization header, https to http too); any
    3xx is an error, and on a create it is named as possibly created."""

    STATUSES = (301, 302, 307, 308)
    IN_FLIGHT = "possibly created: {} was in flight; GHL may hold it; a dry run shows which.\n"

    def test_3xx_on_the_first_create_is_in_flight(self):
        in_flight = self.IN_FLIGHT.format("tag 'call-booked'")
        for status in self.STATUSES:
            for saved in (True, False):
                fake = RedirectOnPost(1, status, saved)
                code, out = self.run_cli(fake, extra=["--apply"])
                case = (status, saved, out)
                self.assertEqual(code, 1, case)
                self.assertEqual(len(fake.writes()), 1, case)       # nothing sent to the target
                self.assertIn(in_flight, out, case)
                self.assertIn("error: --apply stopped part-way: POST /locations/{}/tags -> HTTP {}: a "
                              "redirect, refused and not followed".format(LOC, status), out, case)
                self.assertNotIn("nothing was created", out, case)
                self.assertNotIn("already created", out, case)
                self.assertNotIn(TOKEN, out, case)
                code, out = self.run_cli(fake)
                self.assertRegex(out, r"(?m)^tag +call-booked +{}$".format(
                    "exists" if saved else "will create"), case)

    def test_3xx_on_a_later_create_lists_the_earlier_ones(self):
        for status in self.STATUSES:
            fake = RedirectOnPost(4, status)
            code, out = self.run_cli(fake, extra=["--apply"])
            case = (status, out)
            self.assertEqual(code, 1, case)
            self.assertEqual(len(fake.writes()), 4, case)
            self.assertIn("already created before the error: tag 'call-booked', tag 'call-cancelled', "
                          "pipeline 'Call Booked Pipeline'\n", out, case)
            self.assertIn(self.IN_FLIGHT.format("field 'call_time'"), out, case)

    def test_3xx_on_a_read_exit_1_without_writes(self):
        for status in self.STATUSES + (300, 303, 304):
            def transport(method, url, headers, body, status=status):
                return status, {"Location": "http://evil.example.com/steal"}
            code, out = self.run_cli(transport, extra=["--apply"])
            self.assertEqual(code, 1, out)
            self.assertIn("GET /opportunities/pipelines -> HTTP {}: a redirect, refused".format(status), out)
            self.assertNotIn(TOKEN, out)

    def test_the_urllib_transport_sends_nothing_to_the_redirect_target(self):
        url = gp.BASE_URL + "/locations/{}/tags".format(LOC)
        headers = {"Authorization": "Bearer " + TOKEN, "User-Agent": gp.USER_AGENT}
        for status in self.STATUSES + (303,):
            for target in ("http://evil.example.com/steal", "https://evil.example.com/steal",
                           "http://services.leadconnectorhq.com/locations/{}/tags".format(LOC), "/elsewhere"):
                for method, body in (("GET", None), ("POST", b'{"name": "x"}')):
                    def answer(scheme, host, m, selector, hdrs, data, status=status, target=target):
                        if host == gp.API_HOST and scheme == "https" and selector.startswith("/locations/"):
                            return _raw_answer(status, headers=[("Location", target)])
                        return _raw_answer(200, b'{"stolen": true}')
                    case = (status, target, method)
                    with FakeWire(answer) as wire:
                        with self.assertRaises(gp.GHLRedirectError, msg=repr(case)) as ctx:
                            gp.urllib_transport(method, url, dict(headers), body)
                    self.assertEqual(ctx.exception.status, status, case)
                    self.assertEqual([(s[0], s[1], s[2], s[3]) for s in wire.sent],
                                     [("https", gp.API_HOST, method, "/locations/{}/tags".format(LOC))], case)
                    self.assertNotIn(TOKEN, str(ctx.exception))

    def test_a_full_apply_through_urllib_names_the_redirected_create(self):
        def answer(scheme, host, method, selector, headers, body):
            if host != gp.API_HOST or scheme != "https":
                return _raw_answer(200, b'{"stolen": true}')
            if method == "GET":
                return _raw_answer(200, json.dumps(_account_reads(selector)).encode("utf-8"))
            return _raw_answer(302, headers=[("Location", "http://evil.example.com/steal")])

        with FakeWire(answer) as wire:
            code, out = self.run_cli(gp.urllib_transport, extra=["--apply"])
        self.assertEqual(code, 1, out)
        self.assertIn(self.IN_FLIGHT.format("tag 'call-booked'"), out)
        self.assertNotIn("nothing was created", out)
        self.assertNotIn(TOKEN, out)
        self.assertTrue(all(s[:2] == ("https", gp.API_HOST) for s in wire.sent), wire.sent)
        self.assertEqual([s[2] for s in wire.sent], ["GET"] * 4 + ["POST"])


class TestEnvFilePermissions(Base):
    """Least privilege, item 4: a .env readable by group or others gets a
    one-line warning to chmod 600 it; never the token, a part of it or its
    length. Warn only: the run goes on."""

    def write_env(self, mode):
        if os.path.exists(self.env_path):
            os.unlink(self.env_path)
        with open(self.env_path, "w", encoding="utf-8") as fh:
            fh.write("GHL_PIT_TOKEN={}\nGHL_LOCATION_ID={}\n".format(TOKEN, LOC))
        os.chmod(self.env_path, mode)

    def expected(self, mode):
        return "warning: {} can be accessed by other users (permissions {:o}); run: chmod 600 {}".format(
            self.env_path, mode, self.env_path)

    def test_loose_env_file_warns_once_and_the_run_goes_on(self):
        for mode in (0o644, 0o640, 0o604, 0o660, 0o666, 0o610, 0o601, 0o670, 0o607, 0o777):
            self.write_env(mode)
            fake = full_account()
            code, out = self.run_cli(fake, environ={})
            self.assertEqual(code, 0, (oct(mode), out))
            self.assertEqual(fake.calls[0][2]["Authorization"], "Bearer " + TOKEN)
            warnings = [line for line in out.splitlines() if "chmod" in line]
            self.assertEqual(warnings, [self.expected(mode)], oct(mode))
            self.assertEqual(out.splitlines()[0], self.expected(mode))
            self.assertNotIn(TOKEN, out)
            self.assertNotIn("SECRET", out)

    def test_private_env_file_no_warning(self):
        for mode in (0o600, 0o400, 0o700):
            self.write_env(mode)
            code, out = self.run_cli(full_account(), environ={})
            self.assertEqual(code, 0, out)
            self.assertNotIn("chmod", out)
            self.assertNotIn("warning", out)

    def test_no_env_file_no_warning(self):
        code, out = self.run_cli(full_account())
        self.assertEqual(code, 0, out)
        self.assertNotIn("chmod", out)

    def test_load_credentials_warns_through_the_callback(self):
        self.write_env(0o644)
        said = []
        token, loc = gp.load_credentials(None, self.env_path, {}, warn=said.append)
        self.assertEqual((token, loc), (TOKEN, LOC))
        self.assertEqual(said, [self.expected(0o644)])
        self.write_env(0o600)
        said = []
        gp.load_credentials(None, self.env_path, {}, warn=said.append)
        self.assertEqual(said, [])

    def test_warning_comes_before_a_refused_token(self):
        with open(self.env_path, "w") as fh:
            fh.write("GHL_PIT_TOKEN=pit-SECRET-left\tright-SECRET\n")
        os.chmod(self.env_path, 0o644)
        fake = FakeGHL()
        code, out = self.run_cli(fake, environ={})
        self.assertEqual(code, 2, out)
        self.assertEqual(fake.calls, [])
        self.assertEqual(out.splitlines()[0], self.expected(0o644))
        self.assertIn("error: GHL_PIT_TOKEN has whitespace", out)
        self.assertNotIn("SECRET", out)


class TestUserAgent(Base):
    """Item 5: GHL's API sits behind Cloudflare, which refuses Python's
    default User-Agent (403, error 1010). Every request carries ours, and a
    1010 reads as a clear error with the token redacted."""

    UA = "AdveroSolutions-ghl-prereqs/1.0"

    def test_every_request_carries_the_user_agent(self):
        self.assertEqual(gp.USER_AGENT, self.UA)
        fake = FakeGHL()
        spec = _named_field_spec()
        self.run_cli(fake, spec)
        code, out = self.run_cli(fake, spec, extra=["--apply"])
        self.assertEqual(code, 0, out)
        self.assertEqual(len(fake.writes()), 7)
        for call in fake.calls:
            self.assertEqual(call[2].get("User-Agent"), self.UA, call[:2])

    def test_urllib_sends_it_instead_of_pythons_own(self):
        def answer(scheme, host, method, selector, headers, body):
            if method == "GET":
                return _raw_answer(200, json.dumps(_account_reads(selector)).encode("utf-8"))
            return _raw_answer(201, b'{"tag": {"id": "t1", "name": "x"}}')

        with FakeWire(answer) as wire:
            self.run_cli(gp.urllib_transport, extra=["--apply"])
        self.assertTrue(wire.sent)
        for sent in wire.sent:
            agents = [v for k, v in sent[4].items() if k.lower() == "user-agent"]
            self.assertEqual(agents, [self.UA], sent[:4])

    def test_cloudflare_1010_reads_as_a_clear_error(self):
        page = ("<html><title>Access denied | services.leadconnectorhq.com used Cloudflare</title>"
                "Error 1010 ... The owner of this website has banned your access based on your "
                "browser's signature. ")
        for payload in (lambda h: page + h["Authorization"], lambda h: {"error": "error code: 1010",
                                                                        "echo": h["Authorization"]}):
            def transport(method, url, headers, body, payload=payload):
                return 403, payload(headers)
            code, out = self.run_cli(transport)
            self.assertEqual(code, 1, out)
            self.assertIn("error: GET /opportunities/pipelines -> HTTP 403: GHL's firewall refused the "
                          "request (Cloudflare 1010, User-Agent): ", out)
            self.assertNotIn(TOKEN, out)
            self.assertIn("<GHL_PIT_TOKEN>", out)

    def test_cloudflare_1010_on_a_create_is_not_in_flight(self):
        class FirewallOnSecondPost(FakeGHL):
            def __call__(self, method, url, headers, body):
                if method == "POST" and len(self.writes()) == 1:
                    self.calls.append((method, url[len(gp.BASE_URL):], dict(headers), None))
                    return 403, "error code: 1010"
                return FakeGHL.__call__(self, method, url, headers, body)
        code, out = self.run_cli(FirewallOnSecondPost(), extra=["--apply"])
        self.assertEqual(code, 1, out)
        self.assertIn("already created before the error: tag 'call-booked'\n", out)
        self.assertIn("HTTP 403: GHL's firewall refused the request (Cloudflare 1010, User-Agent)", out)
        self.assertNotIn("possibly created", out)

    def test_another_403_is_not_labelled_a_firewall_refusal(self):
        def transport(method, url, headers, body):
            return 403, {"message": "The token does not have access to this location"}
        code, out = self.run_cli(transport)
        self.assertEqual(code, 1, out)
        self.assertIn("HTTP 403: {", out)
        self.assertNotIn("firewall", out)


# -- hardening round after the allowlist max review (non-blocking notes) -----
def _assert_refused(test, method, path, body=None, reason=None, location=LOC):
    return TestEndpointAllowlist.assert_refused(test, method, path, body, reason, location)


class TestUnparsableHost(Base):
    """Note 1: a lone [ or ], or a look-alike of / # @ in the host, made
    urlsplit raise ValueError: nothing was sent, yet a create was named
    possibly created and a read exited 2. Now it is a RequestRefused."""

    HOST_TRICKS = ("[x/tags", "]x/tags", "[", "]", ":[/x", ".com]/x",
                   "[x/locations/{}/tags".format(LOC), "]/locations/{}/tags".format(LOC),
                   "＃x/tags", "／evil/tags", "＠evil/tags")

    def test_refused_before_sending(self):
        for path in self.HOST_TRICKS:
            for method in ("GET", "POST"):
                body = {"name": "x"} if method == "POST" else None
                _assert_refused(self, method, path, body, "the host is not services.leadconnectorhq.com")
                with self.assertRaises(gp.RequestRefused, msg=repr(path)):
                    gp.check_request(method, gp.BASE_URL + path, LOC, body)

    def test_a_refused_first_create_is_not_possibly_created(self):
        def create_tag(client, name):
            return client.request("POST", "[x/tags", {"name": name})

        fake = FakeGHL()
        with mock.patch.object(gp.GHLClient, "create_tag", create_tag):
            code, out = self.run_cli(fake, extra=["--apply"])
        self.assertEqual(code, 1, out)
        self.assertEqual(fake.writes(), [])
        self.assertIn("nothing was created before the error.\n", out)
        self.assertIn("refused before sending: the host is not services.leadconnectorhq.com", out)
        self.assertNotIn("possibly created", out)
        self.assertNotIn(TOKEN, out)

    def test_a_refused_later_create_lists_the_earlier_ones(self):
        def create_field(client, name, data_type):
            return client.request("POST", "]x/customFields", {"name": name})

        fake = FakeGHL()
        with mock.patch.object(gp.GHLClient, "_create_field", create_field):
            code, out = self.run_cli(fake, extra=["--apply"])
        self.assertEqual(code, 1, out)
        self.assertEqual(len(fake.writes()), 3)
        self.assertIn("already created before the error: tag 'call-booked', tag 'call-cancelled', "
                      "pipeline 'Call Booked Pipeline'\n", out)
        self.assertNotIn("possibly created", out)

    def test_a_refused_read_exits_1_without_writes(self):
        for path in ("[x/tags", "＃x/tags"):
            def tags(client, path=path):
                return client.read_list(path, "tags")

            fake = FakeGHL()
            with mock.patch.object(gp.GHLClient, "tags", tags):
                code, out = self.run_cli(fake, extra=["--apply"])
            self.assertEqual(code, 1, (path, out))
            self.assertEqual(fake.writes(), [], path)
            self.assertIn("refused before sending", out, path)
            self.assertNotIn(TOKEN, out)


class TestGetWithABody(Base):
    """Note 2: a GET never carries a body (one could name another location)."""

    BODIES = ({"locationId": OTHER_LOC}, {"locationId": LOC}, {}, {"name": "x"}, [], "", 0, False)

    def test_refused_on_every_allowed_read(self):
        reads = sorted(p for m, p in gp.allowed_requests(LOC) if m == "GET")
        self.assertEqual(len(reads), 4)
        for path in reads:
            for body in self.BODIES:
                _assert_refused(self, "GET", path, body, "a GET never carries a body")

    def test_the_tools_own_reads_still_go_out(self):
        for path in sorted(p for m, p in gp.allowed_requests(LOC) if m == "GET"):
            rec = Recorder()
            gp.GHLClient(TOKEN, LOC, rec).request("GET", path)
            self.assertEqual([(c[0], c[1], c[3]) for c in rec.calls], [("GET", gp.BASE_URL + path, None)])


class TestMethodIsRedacted(Base):
    """Note 3: the method text in a refusal goes through redact too."""

    def test_a_token_in_the_method_is_redacted(self):
        for method in (TOKEN, "X" + TOKEN, TOKEN + "\n"):
            text = _assert_refused(self, method, "/locations/{}/tags".format(LOC), None,
                                   "is never used by this tool")
            self.assertIn("<GHL_PIT_TOKEN>", text)


class TestCloudflareWording(Base):
    """Note 4: only Cloudflare's own wording is labelled a firewall refusal
    (a trace id holding 1010 is not); every 403 on a create is still GHL
    refusing it, never in flight."""

    LABEL = "GHL's firewall refused the request (Cloudflare 1010, User-Agent)"
    CLOUDFLARE = ("error code: 1010", "Error 1010", "ERROR CODE: 1010", "<h1>Error 1010</h1> Access denied",
                  {"error_code": 1010}, '{"error_code":1010}', '{"ERROR_CODE": 1010}',
                  {"title": "Error 1010: Access denied"})
    OTHER = ("a1010b", {"traceId": "a1010b"}, {"message": "Forbidden", "requestId": "req-1010"},
             "ray 10101010", {"code": 1010}, {"error_code": 10100}, "error code: 10100", "terror 1010",
             "error code 1010", {"message": "The token does not have access to this location"})

    def test_only_cloudflares_wording_is_labelled(self):
        for payload, labelled in [(p, True) for p in self.CLOUDFLARE] + [(p, False) for p in self.OTHER]:
            def transport(method, url, headers, body, payload=payload):
                return 403, payload
            code, out = self.run_cli(transport)
            self.assertEqual(code, 1, (payload, out))
            self.assertIn("error: GET /opportunities/pipelines -> HTTP 403: ", out, payload)
            self.assertEqual(self.LABEL in out, labelled, (payload, out))

    def test_every_403_on_a_create_is_a_refusal_not_in_flight(self):
        for payload in self.CLOUDFLARE + self.OTHER:
            class ForbiddenOnSecondPost(FakeGHL):
                def __call__(self, method, url, headers, body, payload=payload):
                    if method == "POST" and len(self.writes()) == 1:
                        self.calls.append((method, url[len(gp.BASE_URL):], dict(headers), None))
                        return 403, payload
                    return FakeGHL.__call__(self, method, url, headers, body)
            code, out = self.run_cli(ForbiddenOnSecondPost(), extra=["--apply"])
            self.assertEqual(code, 1, (payload, out))
            self.assertIn("already created before the error: tag 'call-booked'\n", out, payload)
            self.assertIn("HTTP 403: ", out, payload)
            self.assertNotIn("possibly created", out, payload)


class TestTokenOutsidePrintableAscii(Base):
    """Note 6: a token with any character outside printable ASCII (after the
    outer strip) exits 2 before any call, with a fixed message: never the
    token, a part of it, its length or the character's position (the HTTP
    library's latin-1 error showed the position)."""

    LEFT, RIGHT = "pit-SECRET-left-4417", "right-SECRET-9083"
    CHARS = ("​", "﻿", "‍", "⁠", "é", "ı", "\U0001f600")

    def expected(self):
        return ("error: GHL_PIT_TOKEN has a character outside plain printable ASCII (such as an "
                "invisible zero-width space or byte-order mark), so it is not a valid token: set "
                "GHL_PIT_TOKEN to the token alone, as plain text, in the environment or in {}\n".format(
                    self.env_path))

    def tokens(self, char):
        return (self.LEFT + char + self.RIGHT, char + self.LEFT + self.RIGHT, self.LEFT + self.RIGHT + char,
                " " + char + self.LEFT + self.RIGHT + "\n")

    def test_refused_before_any_call_with_a_fixed_message(self):
        for char in self.CHARS:
            for token in self.tokens(char):
                fake = FakeGHL()
                code, out = self.run_cli(fake, extra=["--apply"],
                                         environ={"GHL_PIT_TOKEN": token, "GHL_LOCATION_ID": LOC})
                case = (char, token)
                self.assertEqual(code, 2, (case, out))
                self.assertEqual(fake.calls, [], case)
                self.assertEqual(out, self.expected(), case)
                self.assertEqual(os.listdir(self.catalog), [], case)
                with self.assertRaises(gp.ConfigError, msg=repr(case)) as ctx:
                    gp.load_credentials(None, self.env_path, {"GHL_PIT_TOKEN": token})
                self.assertEqual("error: " + str(ctx.exception) + "\n", self.expected(), case)

    def test_nothing_reaches_the_real_opener(self):
        def answer(scheme, host, method, selector, headers, body):
            return _raw_answer(200, json.dumps(_account_reads(selector)).encode("utf-8"))

        for char in ("​", "﻿"):
            with FakeWire(answer) as wire:
                code, out = self.run_cli(gp.urllib_transport, extra=["--apply"],
                                         environ={"GHL_PIT_TOKEN": self.LEFT + char + self.RIGHT,
                                                  "GHL_LOCATION_ID": LOC})
            self.assertEqual(code, 2, out)
            self.assertEqual(wire.sent, [])
            self.assertEqual(out, self.expected())

    def test_from_the_env_file_too(self):
        with open(self.env_path, "w", encoding="utf-8") as fh:
            fh.write("GHL_PIT_TOKEN=﻿{}{}\n".format(self.LEFT, self.RIGHT))
        os.chmod(self.env_path, 0o600)
        fake = FakeGHL()
        code, out = self.run_cli(fake, environ={})
        self.assertEqual(code, 2, out)
        self.assertEqual(fake.calls, [])
        self.assertEqual(out, self.expected())

    def test_printable_ascii_tokens_still_run(self):
        for token in ("!" + TOKEN + "~", "a", "!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~"):
            fake = full_account()
            code, out = self.run_cli(fake, environ={"GHL_PIT_TOKEN": token, "GHL_LOCATION_ID": LOC})
            self.assertEqual(code, 0, (token, out))
            self.assertEqual(fake.calls[0][2]["Authorization"], "Bearer " + token)


class TestEmptyLocation(Base):
    """Note 7: an explicitly empty --location is a ConfigError (exit 2, no
    call), never a quiet fall back to GHL_LOCATION_ID or the default."""

    MESSAGE = ("error: --location is empty: pass the GHL location id (10 to 40 letters and digits), or "
               "leave --location out to use GHL_LOCATION_ID. Nothing was sent.\n")

    def test_exit_2_before_any_call(self):
        for extra in (["--location", ""], ["--location="]):
            for how in ("env", "file", "default"):
                environ = {"GHL_PIT_TOKEN": TOKEN}
                if how == "env":
                    environ["GHL_LOCATION_ID"] = LOC
                elif how == "file":
                    with open(self.env_path, "w", encoding="utf-8") as fh:
                        fh.write("GHL_LOCATION_ID={}\n".format(LOC))
                    os.chmod(self.env_path, 0o600)
                fake = full_account()
                code, out = self.run_cli(fake, extra=extra + ["--apply"], environ=environ)
                if os.path.exists(self.env_path):
                    os.unlink(self.env_path)
                case = (extra, how)
                self.assertEqual(code, 2, (case, out))
                self.assertEqual(fake.calls, [], case)
                self.assertEqual(out, self.MESSAGE, case)
                self.assertEqual(os.listdir(self.catalog), [], case)

    def test_load_credentials_refuses_it(self):
        with self.assertRaises(gp.ConfigError):
            gp.load_credentials("", self.env_path, {"GHL_PIT_TOKEN": TOKEN, "GHL_LOCATION_ID": LOC})
        self.assertEqual(gp.load_credentials(None, self.env_path, {"GHL_PIT_TOKEN": TOKEN,
                                                                   "GHL_LOCATION_ID": LOC}), (TOKEN, LOC))


class TestRedirect303ThroughTheCommandLine(Base):
    """Note 8: a 303 (See Other, which urllib would turn into a GET to the
    target) through run() and the real opener with a fake connection:
    refused, not followed, nothing sent to the target."""

    IN_FLIGHT = TestRedirectsAreNeverFollowed.IN_FLIGHT
    TARGETS = ("http://evil.example.com/steal", "https://evil.example.com/steal", "/elsewhere")

    def wire_answer(self, target, post_at=None, on_read=False):
        posts = []

        def answer(scheme, host, method, selector, headers, body):
            if host != gp.API_HOST or scheme != "https" or not selector.startswith(("/locations/",
                                                                                    "/opportunities/")):
                return _raw_answer(200, b'{"stolen": true}')
            if method == "GET":
                if on_read:
                    return _raw_answer(303, headers=[("Location", target)])
                return _raw_answer(200, json.dumps(_account_reads(selector)).encode("utf-8"))
            posts.append(selector)
            if len(posts) == post_at:
                return _raw_answer(303, headers=[("Location", target)])
            return _raw_answer(201, b"{}")
        return answer

    def assert_only_the_api(self, wire):
        self.assertTrue(all(s[:2] == ("https", gp.API_HOST) for s in wire.sent), wire.sent)
        self.assertTrue(all(s[3].startswith(("/locations/", "/opportunities/")) for s in wire.sent), wire.sent)

    def test_303_on_the_first_create(self):
        for target in self.TARGETS:
            with FakeWire(self.wire_answer(target, post_at=1)) as wire:
                code, out = self.run_cli(gp.urllib_transport, extra=["--apply"])
            self.assertEqual(code, 1, (target, out))
            self.assertIn(self.IN_FLIGHT.format("tag 'call-booked'"), out, target)
            self.assertIn("error: --apply stopped part-way: POST /locations/{}/tags -> HTTP 303: a redirect, "
                          "refused and not followed".format(LOC), out, target)
            self.assertNotIn("nothing was created", out, target)
            self.assertNotIn(TOKEN, out)
            self.assert_only_the_api(wire)
            self.assertEqual([s[2] for s in wire.sent], ["GET"] * 4 + ["POST"], target)

    def test_303_on_a_later_create_lists_the_earlier_ones(self):
        with FakeWire(self.wire_answer(self.TARGETS[0], post_at=4)) as wire:
            code, out = self.run_cli(gp.urllib_transport, extra=["--apply"])
        self.assertEqual(code, 1, out)
        self.assertIn("already created before the error: tag 'call-booked', tag 'call-cancelled', "
                      "pipeline 'Call Booked Pipeline'\n", out)
        self.assertIn(self.IN_FLIGHT.format("field 'call_time'"), out)
        self.assertIn("HTTP 303: a redirect, refused and not followed", out)
        self.assert_only_the_api(wire)
        self.assertEqual([s[2] for s in wire.sent], ["GET"] * 4 + ["POST"] * 4)

    def test_303_on_a_read_exit_1_without_writes(self):
        for target in self.TARGETS:
            with FakeWire(self.wire_answer(target, on_read=True)) as wire:
                code, out = self.run_cli(gp.urllib_transport, extra=["--apply"])
            self.assertEqual(code, 1, (target, out))
            self.assertIn("error: GET /opportunities/pipelines -> HTTP 303: a redirect, refused and not "
                          "followed", out, target)
            self.assertNotIn(TOKEN, out)
            self.assert_only_the_api(wire)
            self.assertEqual([s[2] for s in wire.sent], ["GET"], target)


if __name__ == "__main__":
    unittest.main()
