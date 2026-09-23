"""Make blueprints must read as custom builds, not a generic template.

Every Make-platform spec that exists (vault archetypes, examples, job folders)
is compiled and checked for the tells of the old generic output: `{{1.value}}`
mappers, `#ops` Slack posts the spec never asked for, channels named after a
tool or built from filler words, order numbers posing as channels, the "You
are the step" system prompt, `Sheet1` rows of {now, 1.value}, row columns
mapped to a field of another name, sample numbers/ids/emails standing in as
cell values, `{{now}}` in a duration column, two different set-variable steps
showing the same value, empty canvas notes, and two notes on one module.

    python3 -m pytest -q tests/test_make_quality.py
"""

from __future__ import annotations

import copy
import glob
import json
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from upwork_gen.compile_make import (  # noqa: E402
    channel_name, compile_make, compile_make_with_warnings)
from upwork_gen.generate import available_archetypes, load_archetype  # noqa: E402
from upwork_gen.spec import WorkflowSpec  # noqa: E402

JOBS_DIR = os.path.join(os.path.dirname(ROOT), "upwork-pipeline", "jobs")
SLACK_TRELLO = os.path.join(JOBS_DIR, "slack-trello-drive-team-setup", "spec.json")
WORKIZ = os.path.join(JOBS_DIR, "workiz-quo-openphone-make-openai-sms-automation", "spec.json")

# The readability bar every generated channel has to clear, written out here
# independently of the compiler's own lists.
CHANNEL_RE = re.compile(r"^#[a-z0-9]+(-[a-z0-9]+){0,2}$")
PLATFORM_WORDS = {"slack", "make", "n8n", "zapier", "gmail"}
FILLER_WORDS = {"it", "its", "nothing", "anything", "everything", "every", "has", "have",
                "if", "then", "before", "after", "and", "the", "of", "to", "a", "an",
                "any", "one"}
REF_RE = re.compile(r"^\{\{(\d+)\.(.+)\}\}$")

N8N_RE = re.compile(r"^\s*=|\$json\b|\$\(|\{\{\s*\$")

TOP_KEYS = {"name", "flow", "metadata"}
META_KEYS = {"instant", "version", "scenario", "designer", "zone", "notes"}
SAMPLE_MODULES = {"Sample Input", "Final Output"}


def _load(path):
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if "nodes" not in data and isinstance(data.get("spec"), dict):
        data = data["spec"]
    return data


def make_specs():
    """(name, WorkflowSpec) for every Make-platform spec on disk."""
    out = []
    paths = sorted(glob.glob(os.path.join(ROOT, "vault", "archetypes", "*.json")))
    paths += sorted(glob.glob(os.path.join(ROOT, "examples", "*.json")))
    paths += sorted(glob.glob(os.path.join(JOBS_DIR, "*", "spec.json")))
    for path in paths:
        try:
            data = _load(path)
        except (ValueError, OSError):
            continue
        if not isinstance(data, dict) or data.get("platform") != "make" or "nodes" not in data:
            continue
        out.append((os.path.relpath(path, os.path.dirname(ROOT)), WorkflowSpec.from_dict(data)))
    return out


def walk(flow):
    for module in flow:
        yield module
        for route in module.get("routes") or []:
            for inner in walk(route["flow"]):
                yield inner
        for inner in walk(module.get("onerror") or []):
            yield inner


def is_ascii(text):
    try:
        text.encode("ascii")
    except UnicodeEncodeError:
        return False
    return True


def readable_channel(channel):
    if not CHANNEL_RE.match(channel):
        return False
    return not any(w in PLATFORM_WORDS or w in FILLER_WORDS for w in channel[1:].split("-"))


def key_of(text):
    """"Lead Email" -> "lead_email", "webViewLink" -> "web_view_link"."""
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(text))
    return "_".join(w for w in re.split(r"[^A-Za-z0-9]+", spaced.lower()) if w)


# The status words a row may carry as a literal (a constant on its route).
STATUS_LITERALS = {"ok", "success", "succeeded", "done", "complete", "completed", "posted",
                   "sent", "delivered", "synced", "logged", "written", "saved", "created",
                   "updated", "approved", "published", "drafted", "notified", "booked",
                   "resolved", "processed", "received", "imported", "paid", "queued",
                   "scheduled", "skipped", "escalated", "closed", "awaiting_approval",
                   "needs_review", "needs review", "pending", "failed"}
STATUS_COLUMN_WORDS = {"status", "outcome", "result"}
DURATION_WORDS = {"ms", "sec", "secs", "second", "seconds", "minute", "minutes", "mins",
                  "hour", "hours", "hrs", "day", "days", "duration", "elapsed", "latency",
                  "saved", "estimate", "time", "to", "next", "due"}


def row_columns(module):
    """[(column, value)] for a Sheets row or Airtable record module."""
    mapper = module.get("mapper") or {}
    if "record" in mapper:
        return list(mapper["record"].items())
    spec = module["metadata"]["expect"][0]["spec"]
    return [(c["label"].rsplit(" (", 1)[0], mapper["values"][c["name"]]) for c in spec]


def row_problems(blueprint, module, explicit=()):
    """Why a row's mapping is wrong. Written independently of the compiler:

    * two columns share one reference;
    * a column maps a trigger field whose leaf, parent-qualified name or full
      path is not exactly the column's name, or a set-variable of another
      name (sharing one word is not enough);
    * `{{now}}` in a duration or future-time column;
    * a literal that is not a status word in a status column (sample numbers,
      ids, emails, timestamps and names never stand in for a mapping).

    `explicit` names columns whose value the spec wrote itself."""
    labels = {m["id"]: m for m in walk(blueprint["flow"])}
    problems = []
    seen = {}
    for column, value in row_columns(module):
        value = str(value)
        key = key_of(column)
        words = set(key.split("_"))
        if column in explicit or value == "":
            continue
        if value == "{{now}}":
            if words & DURATION_WORDS:
                problems.append("{!r} gets {{{{now}}}}".format(column))
            continue
        match = REF_RE.match(value)
        if not match:
            if not (words & STATUS_COLUMN_WORDS and value.lower() in STATUS_LITERALS):
                problems.append("{!r} holds the literal {!r}".format(column, value))
            continue
        if value in seen and seen[value] != column:
            problems.append("{!r} and {!r} share {}".format(seen[value], column, value))
        seen.setdefault(value, column)
        module_id, path = int(match.group(1)), match.group(2).replace("`", "")
        parts = path.split(".")
        if module_id == 1:
            names = set()
            for tail in (parts, parts[1:] if parts[0] == "data" else parts):
                if tail:
                    names |= {key_of(tail[-1]), key_of("_".join(tail)),
                              key_of("_".join(tail[-2:]))}
        else:
            target = labels.get(module_id, {})
            names = {parts[0]} if target.get("module", "").startswith("util:SetVariable2") else set()
        if key not in names:
            problems.append("{!r} maps {}, which has another name".format(column, value))
    return problems


def slack_trello_spec():
    if os.path.exists(SLACK_TRELLO):
        return WorkflowSpec.load(SLACK_TRELLO)
    return load_archetype("your_slack_team_hub_trello_and_drive_wired_in")


class TestMakeQualityAcrossSpecs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.specs = make_specs()

    def test_found_make_specs(self):
        self.assertGreaterEqual(len(self.specs), 5, "expected the Make archetypes and job specs")

    def test_blueprints(self):
        for name, spec in self.specs:
            with self.subTest(spec=name):
                self._check(spec)

    def test_every_archetype_compiled_as_make(self):
        """The generic tells must be gone even for n8n archetypes forced to Make."""
        for archetype_id in available_archetypes():
            with self.subTest(archetype=archetype_id):
                spec = load_archetype(archetype_id)
                spec.platform = "make"
                self._check(spec, strict_notes=False)

    def _check(self, spec, strict_notes=True):
        blueprint = compile_make(spec)
        self.assertEqual(set(blueprint), TOP_KEYS)
        self.assertEqual(set(blueprint["metadata"]), META_KEYS)
        json.dumps(blueprint)  # serialisable

        modules = list(walk(blueprint["flow"]))
        ids = [m["id"] for m in modules]
        self.assertEqual(len(ids), len(set(ids)), "duplicate module ids")
        spec_text = json.dumps([spec.input_sample, spec.output_sample,
                                [(n.params, n.notes, n.label) for n in spec.nodes]], ensure_ascii=False)
        # Steps whose own prompt / Slack text held n8n syntax: those are left
        # blank on purpose (never replaced by a generated value).
        n8n_blank = {n.label for n in spec.nodes
                     if N8N_RE.search(json.dumps([(n.params or {}).get("prompt"),
                                                  (n.params or {}).get("text")]))}
        explicit_columns = {n.label: set(n.params["columns"]) for n in spec.nodes
                            if isinstance((n.params or {}).get("columns"), dict)}
        own_system_messages = {
            str(n.params["options"]["systemMessage"]).lstrip("=").strip()
            for n in spec.nodes
            if isinstance((n.params or {}).get("options"), dict)
            and "systemMessage" in n.params["options"]}
        variables = {}

        for module in modules:
            name = module["metadata"]["designer"].get("name")
            mapper = module.get("mapper") or {}
            text = json.dumps(mapper, ensure_ascii=False)
            if spec.input_sample and name not in SAMPLE_MODULES:
                self.assertNotIn("{{1.value}}", text, "generic mapper on {!r}".format(name))
            if name not in SAMPLE_MODULES:
                self.assertTrue(is_ascii(text), "non-ASCII mapper on {!r}".format(name))
                self.assertTrue(is_ascii(json.dumps(module["metadata"].get("expect", []),
                                                    ensure_ascii=False)))
            kind = module["module"]
            if kind.startswith("slack:CreateMessage"):
                channel = str(mapper.get("channel", ""))
                self.assertFalse(re.match(r"^#\d+$", channel), "order number as channel on {!r}".format(name))
                if channel == "#ops":
                    self.assertIn("#ops", spec_text, "#ops on {!r} is not from the spec".format(name))
                # A generated channel is readable; anything else is the spec's own.
                if not channel.startswith("{{") and not readable_channel(channel):
                    self.assertIn(channel.lstrip("#").lower(), spec_text.lower(),
                                  "unreadable channel {!r} on {!r}".format(channel, name))
                if name not in n8n_blank:
                    self.assertIn("{{", mapper.get("text", ""), "Slack text maps no field")
            if kind.startswith("openai-gpt-3:CreateCompletion"):
                system = mapper["messages"][0]["content"]
                self.assertNotIn("You are the step", system)
                if system not in own_system_messages:
                    self.assertIn(spec.title.split()[0], system.replace('"', ""))
                if spec.input_sample and name not in n8n_blank:
                    self.assertIn("{{1.", mapper["messages"][1]["content"])
            if kind.startswith("google-sheets:addRow") or kind.startswith("google-sheets:updateRow"):
                self.assertNotEqual(mapper.get("sheetId"), "Sheet1")
                self.assertNotEqual(mapper.get("values"), {"0": "{{now}}", "1": "{{1.value}}"})
                self.assertGreaterEqual(len(mapper.get("values", {})), 2)
            if kind.split(":")[0] in ("google-sheets", "airtable") and (
                    "values" in mapper or "record" in mapper):
                self.assertEqual(row_problems(blueprint, module, explicit_columns.get(name, ())), [],
                                 "row {!r}".format(name))
            if kind.startswith("util:SetVariable2") and name not in SAMPLE_MODULES:
                value = mapper.get("value")
                self.assertEqual(variables.setdefault(value, name), name,
                                 "{!r} repeats the value of {!r}".format(name, variables.get(value)))

        notes = blueprint["metadata"]["notes"]
        noted_sections = [s for s in spec.sections if s.note or s.label]
        if strict_notes and noted_sections:
            self.assertTrue(notes, "section notes were not emitted")
        for note in notes:
            self.assertEqual(set(note), {"moduleIds", "content", "isFilterNote", "metadata"})
            self.assertIn(note["moduleIds"][0], ids, "note points at a missing module")
            self.assertFalse(note["isFilterNote"])
            self.assertTrue(is_ascii(note["content"]))
            self.assertTrue(note["content"].startswith("<p>"))


class TestSlackTrelloBlueprint(unittest.TestCase):
    def setUp(self):
        self.spec = slack_trello_spec()
        self.blueprint = compile_make(self.spec)
        self.modules = {m["id"]: m for m in walk(self.blueprint["flow"])}

    def by_label(self, fragment):
        return [m for m in self.modules.values()
                if fragment in m["metadata"]["designer"].get("name", "")]

    def test_slack_posts_map_real_trello_and_drive_fields(self):
        card = self.by_label("Post the Card Update")[0]["mapper"]
        self.assertIn("{{1.trello_event.card.name}}", card["text"])
        upload = self.by_label("Post the File Link")[0]["mapper"]
        self.assertIn("{{1.drive_event.file.webViewLink}}", upload["text"])
        self.assertIn("{{1.drive_event.uploaded_by}}", upload["text"])

    def test_slack_channels_come_from_the_spec_samples(self):
        # output_sample.slack_message_card.channel / slack_message_file.channel,
        # and channel_map_used.ops for the failure alert.
        self.assertEqual(self.by_label("Post the Card Update")[0]["mapper"]["channel"], "#team-design")
        self.assertEqual(self.by_label("Post the File Link")[0]["mapper"]["channel"], "#team-writing")
        for alert in self.by_label("Alert Ops That the Post Failed"):
            self.assertEqual(alert["mapper"]["channel"], "#ops")

    def test_pick_the_team_channel_maps_board_and_folder(self):
        value = self.by_label("Pick the Team Channel")[0]["mapper"]["value"]
        self.assertIn("{{1.trello_event.board.name}}", value)
        self.assertIn("{{1.drive_event.folder_path}}", value)
        other = self.by_label("Private Channel Map")[0]["mapper"]["value"]
        self.assertNotEqual(value, other)

    def test_audit_rows_map_only_exact_names(self):
        # No trigger field or set-variable is named team, channel, item or
        # source, so those cells stay blank rather than borrow a lookalike.
        logs = self.by_label("Log Every Notification")
        self.assertEqual(len(logs), 4)
        for log in logs:
            with self.subTest(module=log["id"]):
                self.assertEqual(row_problems(self.blueprint, log), [])
                values = dict(row_columns(log))
                for column in ("source", "team", "channel", "item"):
                    self.assertEqual(values[column], "")

    def test_status_follows_the_posted_ok_branch(self):
        # "7 - Posted OK?" true -> 9 and 14 (posted); false -> 8 "Alert Ops
        # That the Post Failed" -> 11 and 16 (failed).
        status = {m: dict(row_columns(self.modules[m]))["status"] for m in (9, 11, 14, 16)}
        for m in (11, 16):
            self.assertIn("Alert Ops", self.modules[m - 1]["metadata"]["designer"]["name"])
        self.assertEqual(status, {9: "posted", 11: "failed", 14: "posted", 16: "failed"})

    def test_add_row_restore_carries_the_column_captions(self):
        log = self.by_label("Log Every Notification")[0]
        nested = log["metadata"]["restore"]["expect"]["includesHeaders"]
        self.assertEqual(nested["label"], "Yes")
        self.assertEqual(nested["nested"], log["metadata"]["expect"])

    def test_audit_row_columns_come_from_the_output_sample(self):
        log = self.by_label("Log Every Notification")[0]
        labels = [c["label"] for c in log["metadata"]["expect"][0]["spec"]]
        self.assertEqual([l.split(" (")[0] for l in labels],
                         ["timestamp", "source", "team", "channel", "item", "status"])
        values = log["mapper"]["values"]
        self.assertEqual(values["0"], "{{now}}")
        self.assertEqual(values["4"], "")

    def test_one_note_per_section_on_its_first_module(self):
        notes = self.blueprint["metadata"]["notes"]
        self.assertEqual(len(notes), len(self.spec.sections))
        self.assertEqual(notes[0]["moduleIds"], [1])
        self.assertIn("TRELLO AND DRIVE EVENTS COME IN", notes[0]["content"])


@unittest.skipUnless(os.path.exists(WORKIZ), "workiz job spec not on disk")
class TestWorkizBlueprint(unittest.TestCase):
    def setUp(self):
        self.blueprint = compile_make(WorkflowSpec.load(WORKIZ))
        self.modules = {m["id"]: m for m in walk(self.blueprint["flow"])}

    def test_log_rows_map_only_what_their_columns_name(self):
        rows = [m for m in self.modules.values() if m["module"].startswith("google-sheets:")]
        self.assertEqual(len(rows), 2)
        for row in rows:
            with self.subTest(module=row["id"]):
                self.assertEqual(row_problems(self.blueprint, row), [])
                values = dict(row_columns(row))
                self.assertEqual(values["job_id"], "{{1.job_id}}")
                # The sample's thread count and yes/no flag are one run's
                # values, not constants: blank. No branch settles the outcome.
                self.assertEqual(values["outcome"], "")
                self.assertEqual(values["messages_in_thread"], "")
                self.assertEqual(values["ai_suggestion_used_as_is"], "")

    def test_channels(self):
        channels = {m["metadata"]["designer"]["name"]: m["mapper"]["channel"]
                    for m in self.modules.values() if m["module"].startswith("slack:")}
        self.assertEqual(channels, {
            "8 · Suggest Reply to Rep: Approve or Edit": "#general",
            "13 · Alert Me With the Job and What Broke": "#ops-alerts",
        })

    def test_error_trigger_is_drawn_in_the_chain(self):
        """'12 - Any Step in the Scenario Fails' is a webhook module on the main
        chain with its alert right after it: no onerror route, no Ignore, no
        error-handler note, one note per section."""
        flow = self.blueprint["flow"]
        names = [m["metadata"]["designer"].get("name", "") for m in flow]
        i = [k for k, n in enumerate(names) if "Any Step in the Scenario Fails" in n]
        self.assertEqual(len(i), 1)
        self.assertEqual(flow[i[0]]["module"], "gateway:CustomWebHook")
        self.assertIn("Alert Me With the Job", names[i[0] + 1])
        self.assertEqual(flow[i[0] + 1]["module"], "slack:CreateMessage")
        self.assertFalse([m for m in walk(flow) if m.get("onerror") or m["module"] == "builtin:Ignore"])
        notes = self.blueprint["metadata"]["notes"]
        self.assertFalse([n for n in notes if "Error handl" in n["content"]])
        self.assertEqual(len({n["moduleIds"][0] for n in notes}), len(notes))


class TestChannelName(unittest.TestCase):
    """explicit param -> #name in the label -> sample under a channel key ->
    #ops-alerts for a failure -> #general. Nothing else makes a channel."""

    def test_explicit_param_is_emitted_as_written(self):
        cases = [
            ({"channel": "#team_design"}, "#team_design"),
            ({"channel": "#n8n-alerts"}, "#n8n-alerts"),
            ({"channel": "slack-alerts"}, "#slack-alerts"),
            ({"channel": "C08ABC1234"}, "C08ABC1234"),
            ({"channel": "{{1.channel}}"}, "{{1.channel}}"),
            ({"channelId": {"__rl": True, "mode": "name", "value": "#Sales_Desk"}}, "#Sales_Desk"),
            ({"channelId": {"__rl": True, "mode": "list", "value": "C0123ABCDEF",
                            "cachedResultName": "dispatch"}}, "#dispatch"),
        ]
        for params, expected in cases:
            with self.subTest(params=params):
                self.assertEqual(channel_name("Alert on Failure", params=params,
                                              samples=[{"channel": "#crew"}]), expected)
        # n8n syntax is not a channel: the rest of the chain decides.
        self.assertEqual(channel_name("Post It", params={"channel": "={{ $json.channel }}"}), "#general")

    def test_label_channel_beats_samples(self):
        samples = [{"slack": {"channel": "#queue"}}]
        self.assertEqual(channel_name("Notify #content", samples=samples), "#content")
        self.assertEqual(channel_name("Flag Incomplete Submission → #ops", samples=samples), "#ops")
        self.assertEqual(channel_name("Flag Order #1234", samples=samples), "#queue")

    def test_samples_count_only_under_channel_keys(self):
        self.assertEqual(channel_name("Ping", samples=[{"channel": "#crew"}]), "#crew")
        self.assertEqual(channel_name("Ping", samples=[{"assigned_to": "#sales · Marcus Reyes"}]), "#sales")
        digest = [{"alerts": {"channel": "#dispatch-board"}, "digest": {"channel": "#owners"}}]
        self.assertEqual(channel_name("Send the Digest", samples=digest), "#owners")
        for sample in ({"order": "#40911"}, {"ticket": "#1188"}, {"caption": "#roofing"},
                       {"hashtags": ["#roofing"]}, {"brand_color": "#ff5500"}, {"channel": "#1234"}):
            with self.subTest(sample=sample):
                self.assertEqual(channel_name("Post the Caption", samples=[sample]), "#general")
        # The only channel in the samples never takes a failure alert.
        self.assertEqual(channel_name("Alert With the Failed Step",
                                      samples=[{"slack": {"channel": "#closed-won"}}]), "#ops-alerts")

    def test_otherwise_ops_alerts_or_general(self):
        self.assertEqual(channel_name("Alert Me With the Job and What Broke"), "#ops-alerts")
        for label, section in (("Notify the Assigned Rep of the New Lead", ""),
                               ("Approve the Refund", "4 - Finance"),
                               ("Ping", "Account Manager Sign-Off"),
                               ("Ping", "When They Reply On WhatsApp"),
                               ("Ping", "3 - DECIDE"), ("2 - If Any of It", "")):
            with self.subTest(label=label, section=section):
                self.assertEqual(channel_name(label, section), "#general")


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


def _modules(spec):
    return {m["metadata"]["designer"]["name"]: m for m in walk(compile_make(spec)["flow"])}


class TestSpecParamsWin(unittest.TestCase):
    HOOK = {"key": "hook", "kind": "trigger.webhook", "label": "1 - Lead Arrives", "section": "in"}

    def test_defaults_use_general_channel_and_nested_fields(self):
        spec = _spec([self.HOOK, {"key": "s", "kind": "app.action", "app": "slack", "op": "post",
                                  "label": "2 - Alert Sales About the Lead Email", "section": "in"}],
                     [{"from": "hook", "to": "s"}])
        slack = _modules(spec)["2 - Alert Sales About the Lead Email"]["mapper"]
        self.assertEqual(slack["channel"], "#general")
        self.assertIn("{{1.lead.email}}", slack["text"])

    def test_slack_ai_sheets_http_shorthands(self):
        nodes = [
            self.HOOK,
            {"key": "ai", "kind": "ai.llm", "app": "openai", "label": "2 - Draft Reply",
             "params": {"prompt": "Reply to {{1.message}}", "system_message": "Be brief."}},
            {"key": "s", "kind": "app.action", "app": "slack", "op": "post", "label": "3 - Ping",
             "params": {"channel": "sales-desk", "text": "New: {{1.lead.name}}", "mrkdwn": False,
                        "customKnob": 7}},
            {"key": "g", "kind": "app.action", "app": "googleSheets", "op": "append",
             "label": "4 - Log", "params": {"document": "/1abc", "sheet": "Leads",
                                            "columns": ["Name", "Email", "When"]}},
            {"key": "h", "kind": "net.http", "label": "5 - Push",
             "params": {"url": "https://x.test/hook", "method": "PUT",
                        "headers": {"X-Key": "k"}, "body": {"a": "{{1.message}}"}}},
        ]
        edges = [{"from": "hook", "to": "ai"}, {"from": "ai", "to": "s"},
                 {"from": "s", "to": "g"}, {"from": "g", "to": "h"}]
        mods = _modules(_spec(nodes, edges))

        ai = mods["2 - Draft Reply"]["mapper"]["messages"]
        self.assertEqual(ai[0]["content"], "Be brief.")
        self.assertEqual(ai[1]["content"], "Reply to {{1.message}}")

        slack = mods["3 - Ping"]
        self.assertEqual(slack["mapper"]["channel"], "#sales-desk")
        self.assertEqual(slack["mapper"]["text"], "New: {{1.lead.name}}")
        self.assertIs(slack["mapper"]["mrkdwn"], False)          # real mapper name passes through
        self.assertEqual(slack["parameters"].get("customKnob"), 7)  # unknown stays a parameter
        self.assertNotIn("channel", slack["parameters"])

        sheet = mods["4 - Log"]["mapper"]
        self.assertEqual(sheet["spreadsheetId"], "/1abc")
        self.assertEqual(sheet["sheetId"], "Leads")
        self.assertEqual(sheet["values"]["0"], "{{1.lead.name}}")
        self.assertEqual(sheet["values"]["1"], "{{1.lead.email}}")
        self.assertEqual(sheet["values"]["2"], "{{now}}")

        http = mods["5 - Push"]["mapper"]
        self.assertEqual(http["url"], "https://x.test/hook")
        self.assertEqual(http["method"], "put")
        self.assertEqual(http["headers"], [{"name": "X-Key", "value": "k"}])
        self.assertEqual(json.loads(http["data"]), {"a": "{{1.message}}"})

    def test_ai_prompt_uses_client_and_section(self):
        nodes = [self.HOOK, {"key": "ai", "kind": "ai.llm", "app": "openai", "section": "in",
                             "label": "2 - OpenAI: Qualify the Lead"}]
        spec = _spec(nodes, [{"from": "hook", "to": "ai"}])
        # Works whether or not spec.py knows the optional `client` field yet.
        spec.client = {"name": "Ana", "company": "Brightline Roofing", "industry": "Roofing"}
        ai = _modules(spec)["2 - OpenAI: Qualify the Lead"]["mapper"]["messages"]
        self.assertIn("Brightline Roofing", ai[0]["content"])
        self.assertIn("Qualify the Lead", ai[0]["content"])
        self.assertIn("New leads land here.", ai[0]["content"])
        self.assertNotIn("OpenAI:", ai[0]["content"])
        self.assertIn("{{1.lead.name}}", ai[1]["content"])

    def test_archetype_system_message_wins_over_the_generated_one(self):
        nodes = [self.HOOK, {"key": "ai", "kind": "ai.llm", "app": "openai", "label": "2 - Qualify",
                             "params": {"options": {"systemMessage": "=You score roofing leads."}}}]
        ai = _modules(_spec(nodes, [{"from": "hook", "to": "ai"}]))["2 - Qualify"]["mapper"]
        self.assertEqual(ai["messages"][0]["content"], "You score roofing leads.")
        nodes[1]["params"] = {"options": {"systemMessage": "=Score {{ $json.lead }}"}}
        ai = _modules(_spec(nodes, [{"from": "hook", "to": "ai"}]))["2 - Qualify"]["mapper"]
        self.assertIn("Acme Lead Desk", ai["messages"][0]["content"])

    def test_odd_keys_are_backticked(self):
        nodes = [self.HOOK, {"key": "t", "kind": "data.transform", "label": "2 - Keep the Odd Key"}]
        mods = _modules(_spec(nodes, [{"from": "hook", "to": "t"}]))
        self.assertIn("{{1.`odd key`}}", mods["2 - Keep the Odd Key"]["mapper"]["value"])

    def test_polling_trigger_maps_under_data(self):
        nodes = [{"key": "tick", "kind": "trigger.schedule", "label": "1 - Every Morning"},
                 {"key": "s", "kind": "app.action", "app": "slack", "op": "post",
                  "label": "2 - Post the Lead Name"}]
        mods = _modules(_spec(nodes, [{"from": "tick", "to": "s"}]))
        self.assertIn("{{1.data.lead.name}}", mods["2 - Post the Lead Name"]["mapper"]["text"])
        self.assertEqual(mods["1 - Every Morning"]["mapper"].get("data"), "")


def _row_of(spec, label):
    return dict(row_columns(_modules(spec)[label]))


class TestRowCells(unittest.TestCase):
    """A row cell is an explicit spec value, a status word the route settles,
    a field or set-variable of exactly the column's name, `{{now}}` for a
    written-at column, or blank."""

    HOOK = {"key": "hook", "kind": "trigger.webhook", "label": "Lead Arrives"}

    def _log(self, columns, sample_row, input_sample=None):
        nodes = [self.HOOK, {"key": "g", "kind": "app.action", "app": "googleSheets", "op": "append",
                             "label": "Log the Lead", "params": {"columns": columns}}]
        extra = {"output_sample": {"log": sample_row}}
        if input_sample is not None:
            extra["input_sample"] = input_sample
        return _row_of(_spec(nodes, [{"from": "hook", "to": "g"}], **extra), "Log the Lead")

    def test_only_exact_names_map(self):
        row = self._log(["email", "lead_name", "crm_contact_id", "status", "run_id", "one_pager_url"], {},
                        {"lead": {"name": "Ana"}, "email": "a@x.com", "full_name": "Ana Ruiz",
                         "company": {"state": "CA"}, "record": {"order_id": "o1"},
                         "linkedin_url": "https://linkedin.com/in/ana"})
        self.assertEqual(row, {"email": "{{1.email}}", "lead_name": "{{1.lead.name}}",
                               "crm_contact_id": "", "status": "", "run_id": "", "one_pager_url": ""})
        # Two leaves called "name" and no qualified match: ambiguous, so blank.
        row = self._log(["name"], {}, {"card": {"name": "Q4"}, "board": {"name": "Design"}})
        self.assertEqual(row, {"name": ""})

    def test_now_only_in_written_at_columns(self):
        columns = ["timestamp", "logged_at", "date", "When", "response_time_ms", "time_to_decision",
                   "agent_time_to_send", "time_saved_estimate", "equipment_next_time", "due_at", "time"]
        row = self._log(columns, {})
        self.assertEqual([c for c in columns if row[c] == "{{now}}"], ["timestamp", "logged_at", "date", "When"])

    def test_sample_values_never_stand_in(self):
        sample = {"latency_ms": 2310, "tokens_used": 1247, "record": "recA9f42ab10",
                  "approver": "d.okafor@company.com", "sla_due": "2026-07-31T15:07:44Z",
                  "client": "Maria Delgado Ruiz", "sent": False}
        row = self._log(list(sample), sample)
        self.assertEqual(set(row.values()), {""})

    def test_explicit_column_values_are_kept(self):
        row = self._log({"source": "Website form", "email": "{{1.lead.email}}"}, {})
        self.assertEqual(row, {"source": "Website form", "email": "{{1.lead.email}}"})


class TestStatusFollowsTheRoute(unittest.TestCase):
    """failed only on a route that failed; the sample's status word only on a
    route that succeeded; blank when the route does not say."""

    H = {"key": "hook", "kind": "trigger.webhook", "label": "Lead Arrives"}

    def _status(self, nodes, edges, sample_status, label):
        spec = _spec([self.H] + nodes, edges, output_sample={"log": {"name": "Ana", "status": sample_status}})
        return _row_of(spec, label)["status"]

    def test_adversarial_routes(self):
        log = {"key": "g", "kind": "app.action", "app": "googleSheets", "op": "append", "label": "Log the Lead"}
        alert = {"key": "a", "kind": "app.action", "app": "slack", "op": "post",
                 "label": "Alert Sales About the Hot Lead"}
        self.assertEqual(self._status([alert, log], [{"from": "hook", "to": "a"}, {"from": "a", "to": "g"}],
                                      "notified", "Log the Lead"), "")
        retry = {"key": "r", "kind": "net.http", "label": "Retry the CRM Call on Failure"}
        self.assertEqual(self._status([retry, log], [{"from": "hook", "to": "r"}, {"from": "r", "to": "g"}],
                                      "synced", "Log the Lead"), "")
        gate = {"key": "b", "kind": "flow.branch", "label": "Did the Payment Fail?"}
        tell = {"key": "t", "kind": "app.action", "app": "slack", "op": "post", "label": "Tell Finance"}
        edges = [{"from": "hook", "to": "b"}, {"from": "b", "to": "t", "branch": "true"},
                 {"from": "b", "to": "g", "branch": "false"}]
        self.assertEqual(self._status([gate, tell, log], edges, "paid", "Log the Lead"), "paid")
        edges[1:] = [{"from": "b", "to": "g", "branch": "true"}, {"from": "b", "to": "t", "branch": "false"}]
        self.assertEqual(self._status([gate, tell, log], edges, "paid", "Log the Lead"), "failed")
        route = {"key": "b", "kind": "flow.branch", "label": "Route"}
        failed_log = dict(log, label="Log the Failed Sync")
        self.assertEqual(self._status([route, failed_log], [{"from": "hook", "to": "b"},
                                                            {"from": "b", "to": "g", "branch": "error"}],
                                      "synced", "Log the Failed Sync"), "failed")

    def test_real_archetypes(self):
        # (archetype, row label, column, {route filter name or None: status}).
        # webhook: "Did Anything Fail?" false -> the row (ok); true -> the
        # alert -> the row (failed). lead capture: "Sync Completed Without
        # Errors?" true -> the row (success).
        cases = [("webhook_api_paged_js_sheets_logged", "Write the Run Log Row", "status",
                  {"False": "ok", None: "failed"}),
                 ("lead_capture_dedupe_hubspot_route_monitor", "Log Lead and Routing Result",
                  "sync_status", {"True": "success"})]
        for archetype, label, column, expected in cases:
            with self.subTest(archetype=archetype):
                spec = load_archetype(archetype)
                spec.platform = "make"
                rows = [m for m in walk(compile_make(spec)["flow"])
                        if label in m["metadata"]["designer"].get("name", "")]
                got = {(row.get("filter") or {}).get("name"): dict(row_columns(row))[column] for row in rows}
                self.assertEqual(got, expected)


class TestN8nSyntaxNeverShips(unittest.TestCase):
    HOOK = {"key": "hook", "kind": "trigger.webhook", "label": "1 - Lead Arrives", "section": "in"}

    def test_n8n_values_are_blank_and_reported_plain_values_kept(self):
        nodes = [
            self.HOOK,
            {"key": "ai", "kind": "ai.agent", "label": "2 - Sort It",
             "params": {"system_message": "You triage enquiries.",
                        "prompt": "=Enquiry: {{ $json.body.message }}"}},
            {"key": "ai2", "kind": "ai.llm", "label": "3 - Draft It",
             "params": {"prompt": "Draft a reply to {{1.message}}", "system_message": "Be brief."}},
            {"key": "h", "kind": "net.http", "label": "4 - Push",
             "params": {"url": "https://x.test/hook",
                        "body": {"first_name": "={{ $json.first_name }}", "source": "web"},
                        "jsCode": "return $json;"}},
            {"key": "s", "kind": "app.action", "app": "slack", "op": "post", "label": "5 - Ping",
             "params": {"channel": "#front-desk", "text": "={{ $json.text }}"}},
        ]
        edges = [{"from": "hook", "to": "ai"}, {"from": "ai", "to": "ai2"},
                 {"from": "ai2", "to": "h"}, {"from": "h", "to": "s"}]
        blueprint, warnings = compile_make_with_warnings(_spec(nodes, edges))
        mods = {m["metadata"]["designer"]["name"]: m for m in walk(blueprint["flow"])}
        self.assertEqual(mods["2 - Sort It"]["mapper"]["messages"],
                         [{"role": "system", "content": "You triage enquiries."}, {"role": "user", "content": ""}])
        self.assertEqual(mods["3 - Draft It"]["mapper"]["messages"][1]["content"], "Draft a reply to {{1.message}}")
        self.assertEqual(json.loads(mods["4 - Push"]["mapper"]["data"]), {"first_name": "", "source": "web"})
        self.assertNotIn("jsCode", mods["4 - Push"]["parameters"])
        self.assertEqual(mods["5 - Ping"]["mapper"]["text"], "")
        self.assertEqual(mods["5 - Ping"]["mapper"]["channel"], "#front-desk")
        self.assertNotIn("$json", json.dumps(blueprint))
        text = " ".join(warnings)
        for item in ("2 - Sort It (prompt)", "4 - Push (body)", "5 - Ping (text)", "4 - Push (jsCode)"):
            self.assertIn(item, text)

    def test_warnings_reach_the_build_result(self):
        from upwork_gen.generate import generate_from_spec
        nodes = [self.HOOK, {"key": "ai", "kind": "ai.llm", "label": "2 - Sort It",
                             "params": {"prompt": "={{ $json.x }}"}}]
        result = generate_from_spec(_spec(nodes, [{"from": "hook", "to": "ai"}]).to_dict())
        self.assertTrue([w for w in result.warnings if "2 - Sort It (prompt)" in w])


class TestTriggersOnTheCanvas(unittest.TestCase):
    def test_every_trigger_is_drawn_in_the_chain(self):
        """A second business trigger, an n8n error trigger and a native Make
        error handler are each a webhook module on the main chain, followed by
        their own steps, in spec order: no onerror route, no Ignore, no note."""
        nodes = [{"key": "hook", "kind": "trigger.webhook", "label": "1 - Lead Arrives"},
                 {"key": "s", "kind": "app.action", "app": "slack", "op": "post", "label": "2 - Post the Lead"},
                 {"key": "t2", "kind": "trigger.webhook", "label": "3 - Reply Comes In"},
                 {"key": "g", "kind": "app.action", "app": "googleSheets", "op": "append", "label": "4 - Log It"},
                 {"key": "err", "kind": "trigger.app", "app": "n8n", "op": "error_trigger",
                  "label": "5 - Any Step Fails"},
                 {"key": "a", "kind": "app.action", "app": "slack", "op": "post", "label": "6 - Alert Me"},
                 {"key": "err2", "kind": "trigger.app", "app": "make", "op": "error_handler",
                  "label": "7 - Error Handler"},
                 {"key": "b", "kind": "app.action", "app": "slack", "op": "post", "label": "8 - Alert Ops"}]
        edges = [{"from": "hook", "to": "s"}, {"from": "t2", "to": "g"}, {"from": "err", "to": "a"},
                 {"from": "err2", "to": "b"}]
        blueprint, warnings = compile_make_with_warnings(_spec(nodes, edges, sections=[]))
        flow = blueprint["flow"]
        self.assertEqual([(m["metadata"]["designer"]["name"], m["module"]) for m in flow], [
            ("1 - Lead Arrives", "gateway:CustomWebHook"),
            ("Sample Input", "util:SetVariable2"),
            ("2 - Post the Lead", "slack:CreateMessage"),
            ("3 - Reply Comes In", "gateway:CustomWebHook"),
            ("4 - Log It", "google-sheets:addRow"),
            ("5 - Any Step Fails", "gateway:CustomWebHook"),
            ("6 - Alert Me", "slack:CreateMessage"),
            ("7 - Error Handler", "gateway:CustomWebHook"),
            ("8 - Alert Ops", "slack:CreateMessage"),
            ("Final Output", "util:SetVariable2"),
        ])
        # Drawn like the entry webhook, one step to the right of the last module.
        self.assertEqual(flow[5]["parameters"], flow[0]["parameters"])
        self.assertEqual(flow[5]["mapper"], flow[0]["mapper"])
        self.assertEqual([m["metadata"]["designer"]["x"] for m in flow], [300 * i for i in range(10)])
        self.assertFalse([m for m in walk(flow) if m.get("onerror") or m["module"] == "builtin:Ignore"])
        self.assertEqual(blueprint["metadata"]["notes"], [])
        self.assertEqual(warnings, [])


class TestOneNotePerModule(unittest.TestCase):
    def test_vault_corpus(self):
        """Across every vault archetype compiled as Make, no module carries
        more than one canvas note."""
        for archetype_id in available_archetypes():
            with self.subTest(archetype=archetype_id):
                spec = load_archetype(archetype_id)
                spec.platform = "make"
                pinned = [n["moduleIds"][0] for n in compile_make(spec)["metadata"]["notes"]]
                self.assertEqual(len(pinned), len(set(pinned)), "two notes on one module")


if __name__ == "__main__":
    unittest.main()
