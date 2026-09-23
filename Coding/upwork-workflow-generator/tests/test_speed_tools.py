"""Speed tooling: verify_job checks + genericness lint, finalize, batch, nearest.

    python3 -m pytest -q tests/test_speed_tools.py

Nothing here touches the real job folders, proposals.csv, runs.csv or the
vault: every write goes to a temp directory.
"""

from __future__ import annotations

import contextlib
import csv
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
import unittest.mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from upwork_gen import finalize, verify_job  # noqa: E402
from upwork_gen.classify import classify  # noqa: E402
from upwork_gen.spec import WorkflowSpec  # noqa: E402
from upwork_gen.verify_job import (  # noqa: E402
    beat_lines,
    chart_overlaps,
    check_beats,
    check_n8n,
    check_proposal,
    lint_client,
    lint_n8n,
    preview_length,
    preview_of,
)

WG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REAL_CSV = os.path.join(os.path.dirname(WG), "upwork-pipeline", "proposals.csv")
REAL_JOB = os.path.join(os.path.dirname(WG), "upwork-pipeline", "jobs",
                        "crm-automation-multi-system-api-claude-n8n")

PS_BLOCK = (
    "Lorenzo\n\nP.S. A few other things I've done:\n\n"
    "-> one\n-> two\n-> three\n-> four\n"
)


def make_proposal(preview_len: int = 140, link: str = "https://www.loom.com/share/[LOOMURL]",
                  walks: int = 1, greeting: str = "Hey there") -> str:
    """A proposal whose preview is exactly `preview_len` chars."""
    head = "{} \U0001F44B I built this for you, 1-min video: ".format(greeting)
    pad = preview_len - len(head) - len("https://www.loom")
    assert pad > 0
    opener = head.replace("I built", "I " + "x" * (pad - 1) + " built")
    body = opener + link + "\n\n"
    body += "The video walks through how it works.\n\n" * walks
    body += "I can start [START], draft by [DRAFT].\n\n" + PS_BLOCK
    return body


class TestPreview(unittest.TestCase):
    def test_counts_through_the_first_loom(self):
        text = "  Hi 1-min video: https://www.loom.com/share/abc then https://www.loom.com/x"
        self.assertEqual(preview_of(text), "Hi 1-min video: https://www.loom")
        self.assertEqual(preview_length(text), len("Hi 1-min video: https://www.loom"))

    def test_emoji_counts_as_one(self):
        self.assertEqual(preview_length("\U0001F44B https://www.loom.com/share/x"), 18)

    def test_no_link(self):
        self.assertIsNone(preview_length("no link here"))

    def test_fixture_hits_the_requested_length(self):
        for n in (133, 140, 150):
            self.assertEqual(preview_length(make_proposal(n)), n)


class TestProposalChecks(unittest.TestCase):
    def fails(self, text):
        return check_proposal(text)[0]

    def test_clean_proposal_passes(self):
        self.assertEqual(self.fails(make_proposal()), [])
        self.assertEqual(self.fails(make_proposal(
            link="https://www.loom.com/share/0123abcdef")), [])

    def test_preview_bounds(self):
        self.assertTrue(any("preview is 132" in f for f in self.fails(make_proposal(132))))
        self.assertTrue(any("preview is 151" in f for f in self.fails(make_proposal(151))))
        self.assertEqual(self.fails(make_proposal(133)), [])
        self.assertEqual(self.fails(make_proposal(150)), [])

    def test_missing_link(self):
        text = make_proposal().replace("https://www.loom.com/share/[LOOMURL]", "LINK")
        self.assertTrue(any("no https://www.loom link" in f for f in self.fails(text)))

    def test_malformed_link(self):
        text = make_proposal(link="https://www.loom.com/[LOOMURL]")
        self.assertTrue(any("link must be" in f for f in self.fails(text)))

    def test_em_dash(self):
        text = make_proposal().replace("how it works", "how \u2014 it works")
        self.assertTrue(any("em dash" in f for f in self.fails(text)))

    def test_video_walks_through_exactly_once(self):
        self.assertTrue(any("0 times" in f for f in self.fails(make_proposal(walks=0))))
        self.assertTrue(any("2 times" in f for f in self.fails(make_proposal(walks=2))))
        lower = make_proposal().replace("The video walks", "the VIDEO walks")
        self.assertEqual(self.fails(lower), [])

    def test_four_ps_bullets(self):
        self.assertTrue(any("3 '-> ' lines" in f
                            for f in self.fails(make_proposal().replace("-> four\n", ""))))
        self.assertTrue(any("5 '-> ' lines" in f
                            for f in self.fails(make_proposal() + "-> five\n")))
        self.assertTrue(any("no P.S." in f
                            for f in self.fails(make_proposal().replace("P.S.", "PS"))))

    def test_signature(self):
        text = make_proposal().replace("Lorenzo\n", "Cheers\n")
        self.assertTrue(any("signature" in f for f in self.fails(text)))


class TestBeats(unittest.TestCase):
    def test_limits(self):
        ok = "# heading\n\n" + "\n".join("- beat number {}".format(i) for i in range(8))
        self.assertEqual(len(beat_lines(ok)), 8)
        self.assertEqual(check_beats(ok), [])
        nine = ok + "\n- one too many"
        self.assertTrue(any("9 bullet lines" in f for f in check_beats(nine)))
        long = "- " + " ".join(["word"] * 13)
        self.assertTrue(any("13 words" in f for f in check_beats(long)))
        self.assertEqual(check_beats("- " + " ".join(["word"] * 12)), [])


class TestFinalize(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.job = os.path.join(self.tmp, "some-job")
        os.makedirs(self.job)
        with open(os.path.join(self.job, "proposal.md"), "w", encoding="utf-8") as fh:
            fh.write(make_proposal(140))
        with open(os.path.join(self.job, "jd.txt"), "w", encoding="utf-8") as fh:
            fh.write("url: https://www.upwork.com/jobs/~01\nCRM Sync Job\nmeta line\n\npost\n")
        spec = {
            "title": "Your Lead Router",
            "platform": "n8n",
            "nodes": [
                {"key": "t", "kind": "trigger.webhook", "label": "1 - Lead In"},
                {"key": "a", "kind": "ai.agent", "label": "2 - Score"},
                {"key": "m", "kind": "ai.model", "app": "anthropic", "label": "Claude",
                 "parent": "a"},
                {"key": "s", "kind": "app.action", "app": "slack", "op": "post",
                 "label": "3 - Tell Sales"},
            ],
            "edges": [{"from": "t", "to": "a"}, {"from": "a", "to": "s"}],
        }
        with open(os.path.join(self.job, "spec.json"), "w", encoding="utf-8") as fh:
            json.dump(spec, fh)
        # A temp COPY of the real log, so the append is tested against the real
        # header and the real file is never touched.
        self.csv = os.path.join(self.tmp, "proposals.csv")
        if os.path.exists(REAL_CSV):
            shutil.copyfile(REAL_CSV, self.csv)
        else:
            with open(self.csv, "w", encoding="utf-8") as fh:
                fh.write(",".join(finalize.CSV_HEADER) + "\n")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def run_main(self, *extra):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = finalize.main([self.job, "--no-copy", "--csv", self.csv] + list(extra))
        return code, out.getvalue() + err.getvalue()

    def proposal(self):
        with open(os.path.join(self.job, "proposal.md"), encoding="utf-8") as fh:
            return fh.read()

    def test_fill_replaces_every_placeholder(self):
        text = "Hey there, 1-min video: [N]-min https://www.loom.com/share/[LOOMURL] " \
               "start [START] draft [DRAFT]"
        filled, remaining = finalize.fill(text, "https://www.loom.com/share/abc", 2,
                                          "today", "Friday", "Dana")
        self.assertEqual(remaining, [])
        self.assertIn("Hey Dana,", filled)
        self.assertIn("2-min", filled)
        self.assertIn("https://www.loom.com/share/abc", filled)
        self.assertIn("start today draft Friday", filled)

    def test_fill_reports_what_remains(self):
        _, remaining = finalize.fill("[START] [DRAFT] https://www.loom.com/share/[LOOMURL]",
                                     "https://www.loom.com/share/x", 1, "[START]")
        self.assertIn("[START]", remaining)
        self.assertIn("[DRAFT]", remaining)

    def test_main_writes_logs_and_counts(self):
        with open(self.csv, encoding="utf-8") as fh:
            before = list(csv.reader(fh))
        code, output = self.run_main("--loom", "https://www.loom.com/share/abc123",
                                     "--runtime", "1", "--start", "today",
                                     "--draft", "tomorrow", "--name", "Dana",
                                     "--variant", "test-variant")
        self.assertEqual(code, 0, output)
        text = self.proposal()
        self.assertNotIn("[LOOMURL]", text)
        self.assertNotIn("[START]", text)
        self.assertNotIn("[DRAFT]", text)
        self.assertTrue(text.startswith("Hey Dana"))
        # "Hey there" (9) became "Hey Dana" (8): the recount is printed.
        self.assertIn("preview (139 chars)", output)

        with open(self.csv, encoding="utf-8") as fh:
            after = list(csv.reader(fh))
        self.assertEqual(len(after), len(before) + 1)
        header = after[0]
        row = dict(zip(header, after[-1]))
        self.assertEqual(len(after[-1]), len(header))
        self.assertEqual(row["job_title"], "CRM Sync Job")
        self.assertEqual(row["job_url"], "https://www.upwork.com/jobs/~01")
        self.assertEqual(row["platform"], "n8n")
        self.assertEqual(row["build_slug"], "your-lead-router")
        self.assertEqual(row["node_count"], "3")
        self.assertEqual(row["loom_url"], "https://www.loom.com/share/abc123")
        self.assertEqual(row["opener_variant"], "test-variant")
        self.assertEqual(row["opener_visible_chars"], "139")
        self.assertRegex(row["applied_at"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d$")
        self.assertEqual(row["connects"], "")

    def test_preview_out_of_range_warns_without_editing(self):
        with open(os.path.join(self.job, "proposal.md"), "w", encoding="utf-8") as fh:
            fh.write(make_proposal(150))
        code, output = self.run_main("--loom", "https://www.loom.com/share/abc",
                                     "--runtime", "1", "--start", "today", "--no-log",
                                     "--name", "Christopher")
        self.assertEqual(code, 0)
        self.assertIn("WARNING: preview is 156 chars", output)
        self.assertTrue(self.proposal().startswith("Hey Christopher"))

    def test_refuses_when_start_would_remain(self):
        original = self.proposal()
        code, output = self.run_main("--loom", "https://www.loom.com/share/abc",
                                     "--runtime", "1", "--start", "[START]")
        self.assertEqual(code, 2)
        self.assertIn("REFUSED", output)
        self.assertEqual(self.proposal(), original)

    def test_refuses_when_loomurl_would_remain(self):
        with open(os.path.join(self.job, "proposal.md"), "w", encoding="utf-8") as fh:
            fh.write(make_proposal(140).replace("https://www.loom.com/share/[LOOMURL]",
                                                "https://www.loom.com/share/x [LOOMURL]"))
        original = self.proposal()
        with open(self.csv, encoding="utf-8") as fh:
            before = fh.read()
        code, output = self.run_main("--loom", "https://www.loom.com/share/abc",
                                     "--runtime", "1", "--start", "today")
        self.assertEqual(code, 2)
        self.assertEqual(self.proposal(), original)
        with open(self.csv, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), before)

    def test_append_row_creates_file_with_header(self):
        path = os.path.join(self.tmp, "new.csv")
        finalize.append_row(path, {"applied_at": "x", "loom_url": "y"})
        finalize.append_row(path, {"applied_at": "z"})
        with open(path, encoding="utf-8") as fh:
            rows = list(csv.reader(fh))
        self.assertEqual(rows[0], finalize.CSV_HEADER)
        self.assertEqual(len(rows), 3)

    def test_append_row_repairs_missing_trailing_newline(self):
        path = os.path.join(self.tmp, "nonl.csv")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(",".join(finalize.CSV_HEADER))
        finalize.append_row(path, {"applied_at": "x"})
        with open(path, encoding="utf-8") as fh:
            rows = list(csv.reader(fh))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][0], "x")


def _node(name, kind, params=None, **extra):
    node = {"name": name, "type": kind, "parameters": params or {}, "position": [0, 0]}
    node.update(extra)
    return node


class TestN8nChecksAndLint(unittest.TestCase):
    def workflow(self, nodes, connections=None, pins=2, name="Your Flow"):
        wf = {"name": name, "nodes": nodes, "connections": connections or {}}
        wf["pinData"] = {n["name"]: [{"json": {}}] for n in nodes[:pins]}
        return wf

    def lint(self, *nodes):
        wf = self.workflow(list(nodes))
        return lint_n8n(wf, json.dumps(wf))

    def test_structural_fails(self):
        nodes = [_node("1 - A", "n8n-nodes-base.webhook"), _node("2 - B", "n8n-nodes-base.set")]
        good = self.workflow(nodes, {"1 - A": {"main": [[{"node": "2 - B"}]]}})
        self.assertEqual(check_n8n(good, json.dumps(good), "Your Flow", "x"), [])

        dangling = self.workflow(nodes, {"1 - A": {"main": [[{"node": "9 - Gone"}]]},
                                         "Ghost": {"main": [[{"node": "2 - B"}]]}})
        fails = check_n8n(dangling, json.dumps(dangling), "Your Flow", "x")
        self.assertTrue(any("2 dangling" in f for f in fails), fails)

        one_pin = self.workflow(nodes, pins=1)
        self.assertTrue(any("pinData on 1" in f
                            for f in check_n8n(one_pin, json.dumps(one_pin), "Your Flow", "x")))
        self.assertTrue(any("!= spec title" in f
                            for f in check_n8n(good, json.dumps(good), "Other", "x")))
        cal = self.workflow([_node("1 - A", "n8n-nodes-base.calendlyTrigger"), nodes[1]])
        self.assertTrue(any("calendlyTrigger" in f
                            for f in check_n8n(cal, json.dumps(cal), "Your Flow", "x")))
        raw = json.dumps(good, ensure_ascii=False).replace("2 - B", "2 \u00b7 B")
        self.assertTrue(any("non-ASCII" in f for f in check_n8n(good, raw, "Your Flow", "x")))

    def test_example_com_url(self):
        warns = self.lint(_node("3 - Call API", "n8n-nodes-base.httpRequest",
                                {"url": "https://api.example.com/resource"}))
        self.assertTrue(any("example.com" in w for w in warns), warns)
        clean = self.lint(_node("3 - Call API", "n8n-nodes-base.httpRequest",
                                {"url": "https://api.hubapi.com/x", "note": "jane@example.com"}))
        self.assertFalse(any("example.com" in w for w in clean), clean)

    def test_prompt_equal_to_node_name(self):
        agent = "@n8n/n8n-nodes-langchain.agent"
        for text in ("=4 - Score the Lead", "=Score the Lead",
                     "=4 - Score the Lead\n\nemail: {{ $json.email }}\nname: {{ $json.name }}"):
            warns = self.lint(_node("4 - Score the Lead", agent, {"text": text}))
            self.assertTrue(any("prompt is just its node name" in w for w in warns), text)
        real = self.lint(_node("4 - Score the Lead", agent,
                               {"text": "=Score this roofing lead 0-100 on budget and timeline."}))
        self.assertFalse(any("prompt" in w for w in real))

    def test_reason_for_calling(self):
        warns = self.lint(_node("5 - Slack", "n8n-nodes-base.slack",
                                {"channelId": "C1", "text": "={{ $json.reason_for_calling }}"}))
        self.assertTrue(any("reason_for_calling" in w for w in warns))

    def test_duplicate_webhook_paths(self):
        warns = self.lint(_node("1 - A", "n8n-nodes-base.webhook", {"path": "lead-in"}),
                          _node("1 - B", "n8n-nodes-base.webhook", {"path": "lead-in"}),
                          _node("1 - C", "n8n-nodes-base.webhook", {"path": "other"}))
        self.assertEqual(len([w for w in warns if "webhook path" in w]), 1)

    def test_default_parser_schema(self):
        parser = "@n8n/n8n-nodes-langchain.outputParserStructured"
        warns = self.lint(_node("Schema", parser, {
            "jsonSchemaExample": "{\n  \"summary\": \"text\",\n  \"score\": 1\n}"}))
        self.assertTrue(any("default" in w for w in warns))
        custom = self.lint(_node("Schema", parser, {
            "jsonSchemaExample": "{\"tier\": \"hot\", \"score\": 87}"}))
        self.assertFalse(any("default" in w for w in custom))

    def test_condition_reads_step_number(self):
        cond = lambda right: {"conditions": {"conditions": [  # noqa: E731
            {"leftValue": "={{ $json.score }}", "rightValue": right}]}}
        warns = self.lint(_node("7 - Score High Enough?", "n8n-nodes-base.if", cond(7)))
        self.assertTrue(any("own step number" in w for w in warns))
        warns = self.lint(_node("7b - Keep?", "n8n-nodes-base.filter", cond("7")))
        self.assertTrue(any("own step number" in w for w in warns))
        fine = self.lint(_node("7 - Score 70+?", "n8n-nodes-base.if", cond(70)))
        self.assertFalse(any("step number" in w for w in fine))

    def test_slack_without_channel(self):
        self.assertTrue(any("no channel" in w for w in self.lint(
            _node("8 - Tell", "n8n-nodes-base.slack", {"select": "channel", "text": "x"}))))
        self.assertFalse(any("no channel" in w for w in self.lint(
            _node("8 - Tell", "n8n-nodes-base.slack",
                  {"channelId": {"__rl": True, "value": "#sales", "mode": "name"}}))))

    def test_sheets_without_document(self):
        self.assertTrue(any("documentId" in w for w in self.lint(
            _node("9 - Log", "n8n-nodes-base.googleSheets", {"operation": "append"}))))
        self.assertFalse(any("documentId" in w for w in self.lint(
            _node("9 - Log", "n8n-nodes-base.googleSheets",
                  {"documentId": {"__rl": True, "value": "1AbC", "mode": "id"}}))))


class TestClientLint(unittest.TestCase):
    client = {"name": "Dana Whitfield", "company": "Kestrel Roofing"}

    def test_company_missing_everywhere(self):
        warns = lint_client(self.client, "Your Lead Router", [], "- hi there\n")
        self.assertTrue(any("Kestrel Roofing" in w for w in warns))
        self.assertTrue(any("first name 'Dana'" in w for w in warns))

    def test_company_in_title_and_name_in_beat(self):
        warns = lint_client(self.client, "Kestrel Roofing Lead Router", [], "- Dana, here it is\n")
        self.assertEqual(warns, [])

    def test_built_for_sticky_counts(self):
        wf = {"nodes": [_node("Section", "n8n-nodes-base.stickyNote",
                              {"content": "## Built for Kestrel Roofing"})]}
        warns = lint_client(self.client, "Your Lead Router", [wf], "- Dana, look\n")
        self.assertEqual(warns, [])
        other = {"nodes": [_node("Section", "n8n-nodes-base.stickyNote",
                                 {"content": "## Kestrel Roofing mentioned, no marker"})]}
        warns = lint_client(self.client, "Your Lead Router", [other], "- Dana, look\n")
        self.assertEqual(len(warns), 1)


class TestChartClone(unittest.TestCase):
    def setUp(self):
        self.vault = tempfile.mkdtemp()
        labels = ["Count the list", "Verify every address", "Buy lookalike domains",
                  "Publish SPF DKIM DMARC", "Import mailboxes into Instantly",
                  "Warm up for two weeks"]
        self.write("cold_email_outreach", "Cold Email Outreach Setup", labels)
        self.write("unrelated", "Invoice OCR", ["Read the PDF", "Extract totals",
                                                "Post to QuickBooks"])
        self.write("same_title", "Your Chart", labels)

    def tearDown(self):
        shutil.rmtree(self.vault)

    def write(self, archetype_id, title, labels):
        nodes = [{"key": "n{}".format(i), "kind": "data.transform",
                  "label": "{} - {}".format(i + 1, label)} for i, label in enumerate(labels)]
        with open(os.path.join(self.vault, archetype_id + ".json"), "w") as fh:
            json.dump({"title": title, "platform": "diagram", "nodes": nodes}, fh)

    def chart(self, labels, title="Your Chart"):
        return WorkflowSpec.from_dict({
            "title": title, "platform": "diagram",
            "nodes": [{"key": "n{}".format(i), "kind": "data.transform",
                       "label": "{} - {}".format(i + 1, label)}
                      for i, label in enumerate(labels)]})

    def test_clone_is_flagged_and_own_title_excluded(self):
        spec = self.chart(["Count the whole list", "Verify each address",
                           "Buy lookalike domain names", "Pick the webinar date"])
        hits = chart_overlaps(spec, self.vault)
        self.assertEqual([h[0] for h in hits], ["cold_email_outreach"])
        self.assertEqual(hits[0][1:], (3, 4))

    def test_distinct_chart_passes(self):
        spec = self.chart(["Interview the client", "Map every trade", "Price the job",
                           "Send the estimate"])
        self.assertEqual(chart_overlaps(spec, self.vault), [])


class TestClassifyStripsJdHeader(unittest.TestCase):
    def test_hiring_history_does_not_drive_classification(self):
        post = "We need a RAG chatbot over our knowledge base with a vector database."
        jd = ("url: https://www.upwork.com/jobs/~01\nChatbot build\n"
              "Client record: hired a Shopify developer, Shopify order fulfillment, shipping "
              "and inventory work.\n\n" + post)
        found = classify(jd)
        self.assertNotIn("shopify", found.apps)
        self.assertEqual(found.archetype, "ai_rag_chatbot")

    def test_plain_text_untouched(self):
        text = "line one shopify\nline two\nline three\n\nrest"
        self.assertIn("shopify", classify(text).apps)


@unittest.skipUnless(os.path.isdir(REAL_JOB), "pipeline job folder not present")
class TestBatchAndNearest(unittest.TestCase):
    def test_batch_compiles_copies_and_verifies_in_temp(self):
        from upwork_gen import cli
        tmp = tempfile.mkdtemp()
        try:
            job = os.path.join(tmp, "job")
            os.makedirs(job)
            for name in ("spec.json", "jd.txt", "proposal.md", "beats.md"):
                shutil.copyfile(os.path.join(REAL_JOB, name), os.path.join(job, name))
            out_dir = os.path.join(tmp, "out")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = cli.main(["batch", job, "--no-learn", "--no-log",
                                 "--out-dir", out_dir])
            produced = sorted(os.listdir(job))
            self.assertTrue(any(p.endswith(".n8n.json") for p in produced), produced)
            self.assertTrue(any(p.endswith(".excalidraw") for p in produced), produced)
            self.assertTrue(any(p.endswith(".mmd.md") for p in produced), produced)
            self.assertFalse(any(p.endswith(".dsl") for p in produced), produced)
            self.assertEqual(code, 0, buf.getvalue())
            self.assertIn("upwork url", buf.getvalue())
            self.assertIn("https://www.upwork.com/jobs/", buf.getvalue())
        finally:
            shutil.rmtree(tmp)

    def test_produced_files_skips_stale_and_prefix_collisions(self):
        from upwork_gen.cli import _produced_files
        tmp = tempfile.mkdtemp()
        try:
            for name in ("s.n8n.json", "s--2-form.ghl.json", "s--2-form.ghl-prompt.txt",
                         "s.ghl.json", "s.excalidraw.dsl", "s-2.ghl.json",
                         "s-other-slug.n8n.json", "sx.n8n.json", "s--1-old.ghl.json"):
                open(os.path.join(tmp, name), "w").close()
            os.utime(os.path.join(tmp, "s--1-old.ghl.json"), (1, 1))
            found = sorted(os.path.basename(p) for p in _produced_files(tmp, "s", 100))
            # Only the current slug's own names: `<slug><suffix>` and the
            # `<slug>--<n>-<trigger>` GHL split. A recent `s-other-slug.*` is
            # another spec, and an old file is an older run.
            self.assertEqual(found, ["s--2-form.ghl-prompt.txt", "s--2-form.ghl.json",
                                     "s.ghl.json", "s.n8n.json"])
        finally:
            shutil.rmtree(tmp)

    def test_nearest_lists_param_rich_specs_only(self):
        from upwork_gen.cli import _param_coverage, nearest
        with open(os.path.join(REAL_JOB, "jd.txt"), encoding="utf-8") as fh:
            text = fh.read()
        vault_hits, job_hits = nearest(text, 3, os.path.abspath(REAL_JOB))
        for score, cid, path, with_params, flow in vault_hits + job_hits:
            with open(path, encoding="utf-8") as fh:
                w, f = _param_coverage(json.load(fh))
            self.assertGreaterEqual(w / float(f), 0.3, cid)
            # The post's own spec is never its own style reference.
            self.assertNotIn(os.path.abspath(REAL_JOB), os.path.abspath(path))
        scores = [h[0] for h in vault_hits]
        self.assertEqual(scores, sorted(scores, reverse=True))


class TestVerifyJobEndToEnd(unittest.TestCase):
    def test_missing_everything_fails_cleanly(self):
        tmp = tempfile.mkdtemp()
        try:
            report = verify_job.verify(tmp)
            self.assertTrue(any("spec.json missing" in f for f in report.fails))
            self.assertTrue(any("proposal.md missing" in f for f in report.fails))
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(verify_job.main([tmp]), 1)
        finally:
            shutil.rmtree(tmp)



# --------------------------------------------------------------------------
# Review fixes: batch isolation, stale builds, finalize idempotency, CSV
# line endings, atomic proposal write, GHL split handling, minor items.
# --------------------------------------------------------------------------

UP_JOB = os.path.join(os.path.dirname(WG), "upwork-pipeline", "job")

N8N_SPEC = {
    "title": "Your Lead Router",
    "platform": "n8n",
    "nodes": [
        {"key": "t", "kind": "trigger.webhook", "label": "1 - Lead In"},
        {"key": "a", "kind": "ai.agent", "label": "2 - Score"},
        {"key": "m", "kind": "ai.model", "app": "anthropic", "label": "Claude", "parent": "a"},
        {"key": "s", "kind": "app.action", "app": "slack", "op": "post",
         "label": "3 - Tell Sales"},
    ],
    "edges": [{"from": "t", "to": "a"}, {"from": "a", "to": "s"}],
}
N8N_SLUG = "your-lead-router"


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def make_job(root, name, spec=N8N_SPEC, spec_text=None):
    job = os.path.join(root, name)
    os.makedirs(job)
    _write(os.path.join(job, "spec.json"),
           spec_text if spec_text is not None else json.dumps(spec))
    _write(os.path.join(job, "jd.txt"),
           "url: https://www.upwork.com/jobs/~{}\nTitle\n\npost\n".format(name))
    _write(os.path.join(job, "proposal.md"), make_proposal(140))
    _write(os.path.join(job, "beats.md"), "- Dana, here it is\n")
    return job


class BatchCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.out_dir = os.path.join(self.tmp, "out")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def batch(self, *jobs):
        from upwork_gen import cli
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            code = cli.main(["batch"] + list(jobs) + ["--no-learn", "--no-log",
                                                       "--out-dir", self.out_dir])
        return code, buf.getvalue()


class TestBatchIsolation(BatchCase):
    """Defect 1: one job's exception never stops the batch, and its row is a
    FAIL built without verifying the stale files still in its folder."""

    def row(self, output, slug):
        lines = [l for l in output.splitlines() if l.strip().startswith(slug + " ")]
        return lines

    def test_bad_json_spec_is_isolated(self):
        bad = make_job(self.tmp, "a-broken", spec_text="{ not json")
        _write(os.path.join(bad, "old-build.n8n.json"), "{}")  # stale, never verified
        good = make_job(self.tmp, "b-good")
        verified = []
        real_verify = verify_job.verify

        def spy(job, *a, **k):
            verified.append(os.path.basename(job))
            return real_verify(job, *a, **k)

        with unittest.mock.patch.object(verify_job, "verify", spy):
            code, output = self.batch(bad, good)
        self.assertEqual(code, 1, output)
        self.assertEqual(verified, ["b-good"])  # the broken job is not verified
        self.assertIn("compile failed: JSONDecodeError", output)
        self.assertTrue(any("FAIL" in l for l in self.row(output, "a-broken")), output)
        self.assertTrue(os.path.exists(os.path.join(good, N8N_SLUG + ".n8n.json")))
        self.assertIn("did not compile: a-broken", output)

    def test_write_output_spec_error_and_oserror_are_isolated(self):
        from upwork_gen import cli
        from upwork_gen.spec import SpecError
        jobs = [make_job(self.tmp, n) for n in ("a-spec-error", "b-os-error", "c-good")]
        real = cli.write_output
        calls = []

        def flaky(result, **kwargs):
            calls.append(1)
            if len(calls) == 1:
                raise SpecError("platform refused")
            if len(calls) == 2:
                raise OSError("disk full")
            return real(result, **kwargs)

        with unittest.mock.patch.object(cli, "write_output", flaky):
            code, output = self.batch(*jobs)
        self.assertEqual(code, 1)
        self.assertIn("compile failed: platform refused", output)
        self.assertIn("compile failed: OSError: disk full", output)
        self.assertTrue(os.path.exists(os.path.join(jobs[2], N8N_SLUG + ".n8n.json")))
        self.assertFalse(os.path.exists(os.path.join(jobs[0], N8N_SLUG + ".n8n.json")))
        for slug in ("a-spec-error", "b-os-error"):
            self.assertTrue(any(l.rstrip().endswith("FAIL") for l in self.row(output, slug)),
                            output)

    def test_missing_spec_is_a_compile_failure(self):
        job = os.path.join(self.tmp, "no-spec")
        os.makedirs(job)
        code, output = self.batch(job)
        self.assertEqual(code, 1)
        self.assertIn("compile failed: no spec.json", output)


class TestStaleBuilds(BatchCase):
    """Defect 2: batch retires builds it did not produce, verify fails on
    builds from another slug, and ./job loads only the current slug."""

    def test_batch_moves_unproduced_builds_to_stale(self):
        job = make_job(self.tmp, "renamed")
        _write(os.path.join(job, "old-title.n8n.json"), "OLD")
        _write(os.path.join(job, "old-title.excalidraw"), "OLD")
        _write(os.path.join(job, N8N_SLUG + ".make.json"), "OLD MAKE")  # not produced now
        _write(os.path.join(job, ".stale", "old-title.n8n.json"), "OLDER")
        _write(os.path.join(job, "notes.md"), "mine")
        code, output = self.batch(job)
        names = sorted(n for n in os.listdir(job) if os.path.isfile(os.path.join(job, n)))
        self.assertEqual([n for n in names if verify_job.build_suffix(n)],
                         [N8N_SLUG + ".excalidraw", N8N_SLUG + ".mmd.md",
                          N8N_SLUG + ".n8n.json"], output)
        self.assertIn("notes.md", names)
        stale = sorted(os.listdir(os.path.join(job, ".stale")))
        self.assertEqual(len(stale), 4, stale)  # nothing overwritten, nothing lost
        self.assertEqual(_read(os.path.join(job, ".stale", "old-title.n8n.json")), "OLDER")
        self.assertIn(N8N_SLUG + ".make.json", stale)
        self.assertIn("moved stale builds to .stale/", output)
        report = verify_job.verify(job)
        self.assertFalse(any("not from the current spec" in f for f in report.fails),
                         report.fails)

    def test_verify_fails_on_builds_from_another_slug(self):
        job = make_job(self.tmp, "j")
        for name in (N8N_SLUG + ".n8n.json", N8N_SLUG + ".excalidraw",
                     N8N_SLUG + "--2-form.ghl.json"):
            _write(os.path.join(job, name), "{}")
        report = verify_job.verify(job)
        self.assertFalse(any("not from the current spec" in f for f in report.fails),
                         report.fails)
        for foreign in ("old-title.n8n.json", N8N_SLUG + "-2.ghl.json",
                        N8N_SLUG + "--2-form.n8n.json"):
            _write(os.path.join(job, foreign), "{}")
            report = verify_job.verify(job)
            hits = [f for f in report.fails if "not from the current spec" in f]
            self.assertEqual(len(hits), 1, report.fails)
            self.assertIn(foreign, hits[0])
            os.remove(os.path.join(job, foreign))

    def test_is_current_build(self):
        ok = verify_job.is_current_build
        self.assertTrue(ok("s.n8n.json", "s"))
        self.assertTrue(ok("s--3-appointment-booked.ghl-prereqs.txt", "s"))
        self.assertFalse(ok("s--3-x.n8n.json", "s"))
        self.assertFalse(ok("s.excalidraw.dsl", "s"))
        self.assertFalse(ok("sx.n8n.json", "s"))


@unittest.skipUnless(os.path.exists(UP_JOB) and shutil.which("bash"), "loader not present")
class TestJobLoader(unittest.TestCase):
    """Defect 2, loader half: a sandbox copy of upwork-pipeline/job with fake
    pbcopy/open, a temp HOME and GHL-Imports, and no n8n wake-up."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        pipeline = os.path.join(self.tmp, "upwork-pipeline")
        os.makedirs(os.path.join(pipeline, "jobs"))
        shutil.copy2(UP_JOB, os.path.join(pipeline, "job"))
        os.symlink(WG, os.path.join(self.tmp, "upwork-workflow-generator"))
        self.bin = os.path.join(self.tmp, "bin")
        self.clip = os.path.join(self.tmp, "clipboard")
        _write(os.path.join(self.bin, "pbcopy"), "#!/bin/sh\ncat > '{}'\n".format(self.clip))
        _write(os.path.join(self.bin, "open"), "#!/bin/sh\nexit 0\n")
        for name in ("pbcopy", "open"):
            os.chmod(os.path.join(self.bin, name), 0o755)
        self.imports = os.path.join(self.tmp, "imports")
        self.job = os.path.join(pipeline, "jobs", "my-job")
        os.makedirs(self.job)
        _write(os.path.join(self.job, "spec.json"), json.dumps(N8N_SPEC))
        _write(os.path.join(self.job, "jd.txt"), "url: https://www.upwork.com/jobs/~01\nT\n")
        for note in ("assessment", "beats", "proposal"):
            _write(os.path.join(self.job, note + ".md"), note + "\n")
        self.script = os.path.join(pipeline, "job")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def run_job(self, *args):
        import subprocess
        env = dict(os.environ, PATH=self.bin + os.pathsep + os.environ.get("PATH", ""),
                   HOME=os.path.join(self.tmp, "home"), UPWORK_NO_WARM="1",
                   UPWORK_GHL_IMPORTS=self.imports)
        proc = subprocess.run(["bash", self.script] + list(args), env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              universal_newlines=True, timeout=60)
        return proc.returncode, proc.stdout

    def test_loads_the_current_slug_not_the_alphabetically_first(self):
        _write(os.path.join(self.job, "a-old-title.n8n.json"), "OLD")
        _write(os.path.join(self.job, N8N_SLUG + ".n8n.json"), "NEW")
        code, output = self.run_job("my-job")
        self.assertEqual(code, 0, output)
        self.assertEqual(_read(self.clip), "NEW")
        self.assertIn(N8N_SLUG + ".n8n.json", output)

    def test_only_stale_builds_is_not_compiled(self):
        _write(os.path.join(self.job, "a-old-title.n8n.json"), "OLD")
        code, output = self.run_job("my-job")
        self.assertEqual(code, 1, output)
        self.assertIn("no n8n file for the current spec", output)
        self.assertFalse(os.path.exists(self.clip))

    def test_ghl_split_copies_only_current_files_in_order(self):
        spec = dict(N8N_SPEC, title="Your GHL Flow")
        _write(os.path.join(self.job, "spec.json"), json.dumps(spec))
        for name, body in (("your-ghl-flow--10-late.ghl.json", "TEN"),
                           ("your-ghl-flow--2-booked.ghl.json", "TWO"),
                           ("your-ghl-flow--1-form.ghl.json", "ONE"),
                           ("aaa-old.ghl.json", "OLD"),
                           ("your-ghl-flow-old--1-x.ghl.json", "OTHER")):
            _write(os.path.join(self.job, name), body)
        code, output = self.run_job("my-job")  # default n8n falls through to ghl
        self.assertEqual(code, 0, output)
        self.assertEqual(_read(self.clip), "ONE")
        self.assertEqual(sorted(os.listdir(self.imports)),
                         ["your-ghl-flow--1-form.ghl.json", "your-ghl-flow--10-late.ghl.json",
                          "your-ghl-flow--2-booked.ghl.json"])


class TestFinalizeIdempotency(TestFinalize):
    """Defects 3-5, on the same fixture as TestFinalize."""

    LOOM = "https://www.loom.com/share/abc123"

    def rows(self):
        with open(self.csv, encoding="utf-8") as fh:
            return list(csv.reader(fh))

    def first_run(self):
        code, output = self.run_main("--loom", self.LOOM, "--runtime", "1",
                                     "--start", "today", "--draft", "Friday")
        self.assertEqual(code, 0, output)

    def test_second_run_same_loom_is_a_no_op_for_the_log(self):
        before = len(self.rows())
        self.first_run()
        text = self.proposal()
        code, output = self.run_main("--loom", self.LOOM, "--runtime", "1",
                                     "--start", "today")
        self.assertEqual(code, 0, output)
        self.assertEqual(self.proposal(), text)
        self.assertEqual(len(self.rows()), before + 1)
        self.assertIn("NOT LOGGED", output)
        self.assertIn("--relog", output)
        code, output = self.run_main("--loom", self.LOOM, "--runtime", "1",
                                     "--start", "today", "--relog")
        self.assertEqual(code, 0, output)
        self.assertEqual(len(self.rows()), before + 2)

    def test_different_loom_refuses_without_replace(self):
        self.first_run()
        text = self.proposal()
        rows = self.rows()
        code, output = self.run_main("--loom", "https://www.loom.com/share/zzz999",
                                     "--runtime", "2", "--start", "today")
        self.assertEqual(code, 2)
        self.assertIn("REFUSED", output)
        self.assertIn("--replace-loom", output)
        self.assertEqual(self.proposal(), text)
        self.assertEqual(self.rows(), rows)

    def test_replace_loom_swaps_url_and_runtime(self):
        with open(os.path.join(self.job, "proposal.md"), "w", encoding="utf-8") as fh:
            fh.write(make_proposal(140).replace("1-min", "[N]-min")
                     + "\nHappy to hop on a 30-min call.\n")
        self.first_run()
        self.assertIn("1-min video", self.proposal())
        code, output = self.run_main("--loom", "https://www.loom.com/share/zzz999",
                                     "--runtime", "3", "--start", "today", "--replace-loom")
        self.assertEqual(code, 0, output)
        text = self.proposal()
        self.assertIn("https://www.loom.com/share/zzz999", text)
        self.assertNotIn(self.LOOM, text)
        self.assertIn("3-min video", text)
        self.assertNotIn("1-min", text)
        self.assertIn("30-min call", text)  # the body is not the runtime
        # The logged row follows the proposal in place; no duplicate, no --relog hint.
        self.assertIn("updated loom_url and opener_visible_chars in place", output)
        self.assertNotIn("--relog", output)

    def test_refuses_with_neither_placeholder_nor_loom(self):
        with open(os.path.join(self.job, "proposal.md"), "w", encoding="utf-8") as fh:
            fh.write(make_proposal(140).replace("https://www.loom.com/share/[LOOMURL]",
                                                "https://www.loom.com/"))
        code, output = self.run_main("--loom", self.LOOM, "--runtime", "1",
                                     "--start", "today")
        self.assertEqual(code, 2)
        self.assertIn("neither [LOOMURL]", output)

    def test_appended_row_has_no_carriage_return(self):
        with open(self.csv, "rb") as fh:
            before = fh.read()
        self.first_run()
        with open(self.csv, "rb") as fh:
            after = fh.read()
        self.assertTrue(after.startswith(before))
        appended = after[len(before):]
        self.assertTrue(appended.endswith(b"\n"))
        self.assertNotIn(b"\r", appended)
        path = os.path.join(self.tmp, "fresh.csv")
        finalize.append_row(path, {"applied_at": "x"})
        with open(path, "rb") as fh:
            self.assertNotIn(b"\r", fh.read())

    def test_proposal_write_is_atomic_and_keeps_mode(self):
        path = os.path.join(self.job, "proposal.md")
        os.chmod(path, 0o640)
        self.first_run()
        self.assertEqual(os.stat(path).st_mode & 0o777, 0o640)
        self.assertEqual(sorted(os.listdir(self.job)), ["jd.txt", "proposal.md", "spec.json"])

    def test_failed_replace_leaves_original_and_no_temp(self):
        original = self.proposal()
        with unittest.mock.patch.object(finalize.os, "replace",
                                        side_effect=OSError("boom")):
            with self.assertRaises(OSError):
                self.run_main("--loom", self.LOOM, "--runtime", "1", "--start", "today")
        self.assertEqual(self.proposal(), original)
        self.assertEqual(sorted(os.listdir(self.job)), ["jd.txt", "proposal.md", "spec.json"])


class TestGhlSplitCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def clip(self, files):
        from upwork_gen import cli
        for name, body in files.items():
            _write(os.path.join(self.tmp, name), body)
        dsl = os.path.join(self.tmp, "s.excalidraw.dsl")
        _write(dsl, "x")
        copied = []
        buf = io.StringIO()
        with unittest.mock.patch.object(cli, "OUT_DIR", self.tmp), \
                unittest.mock.patch.object(cli, "latest_run_dsl", lambda: dsl), \
                unittest.mock.patch.object(cli, "clip_copy",
                                           lambda text: copied.append(text) or True), \
                contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            code = cli.main(["clip", "ghl"])
        return code, buf.getvalue(), copied

    def test_split_spec_copies_first_and_lists_all(self):
        code, output, copied = self.clip({"s--2-booked.ghl.json": "TWO",
                                          "s--1-form.ghl.json": "ONE",
                                          "s--10-late.ghl.json": "TEN",
                                          "old--1-x.ghl.json": "OLD"})
        self.assertEqual(code, 0, output)
        self.assertEqual(copied, ["ONE"])
        self.assertIn("3 GHL workflows", output)
        for name in ("s--1-form.ghl.json", "s--2-booked.ghl.json", "s--10-late.ghl.json"):
            self.assertIn(os.path.join(self.tmp, name), output)
        self.assertNotIn("old--1-x", output)
        lines = output.splitlines()
        order = [i for n in ("--1-form", "--2-booked", "--10-late")
                 for i, l in enumerate(lines) if n in l and l.startswith("    ")]
        self.assertEqual(order, sorted(order))

    def test_single_workflow_still_works(self):
        code, output, copied = self.clip({"s.ghl.json": "ONLY"})
        self.assertEqual(code, 0, output)
        self.assertEqual(copied, ["ONLY"])

    def test_report_prints_every_ghl_path(self):
        import types
        from upwork_gen import cli
        from upwork_gen.generate import ROOT

        def result(**extra):
            base = dict(spec=types.SimpleNamespace(title="T"), platform="gohighlevel",
                        engine="compiler", node_count=4, elapsed_ms=1, classification=None,
                        path=None, flow_path=None, dsl_path=None, mockup_path=None,
                        copied=False, workflow={}, layout_problems=[], warnings=[],
                        ghl_json_path=None)
            base.update(extra)
            return types.SimpleNamespace(**base)

        paths = [os.path.join(ROOT, "out", "t--{}-x.ghl.json".format(i)) for i in (1, 2)]
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cli._report(result(ghl_json_path=paths[0], ghl_json_paths=paths))
        self.assertIn("out/t--1-x.ghl.json", buf.getvalue())
        self.assertIn("out/t--2-x.ghl.json", buf.getvalue())
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cli._report(result(ghl_json_path=paths[0]))
        self.assertIn("out/t--1-x.ghl.json", buf.getvalue())


class TestReviewMinors(unittest.TestCase):
    def test_order_reports_missing_folders(self):
        tmp = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(tmp, "real"))
            _write(os.path.join(tmp, "_ORDER.txt"), "ghost\nreal\nlater\n")
            missing = []
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                found = verify_job.order_slugs(2, tmp, missing=missing)
            self.assertEqual(found, [os.path.join(tmp, "real")])
            self.assertEqual(missing, ["ghost"])
            self.assertIn("slug ghost listed in _ORDER.txt has no folder", buf.getvalue())
        finally:
            shutil.rmtree(tmp)

    def test_signature_alone_or_with_trailing_spaces(self):
        for sig in ("Lorenzo\n", "Lorenzo   \n", "Lorenzo  \r\n", "  Lorenzo\n"):
            text = make_proposal().replace("Lorenzo\n", sig)
            self.assertFalse(any("signature" in f for f in check_proposal(text)[0]), sig)
        text = make_proposal().replace("Lorenzo\n", "Lorenzo V.\n")
        self.assertTrue(any("signature" in f for f in check_proposal(text)[0]))

    def test_runtime_placeholder_counts_as_one_char(self):
        filled = make_proposal(140)
        raw = filled.replace("1-min", "[N]-min")
        self.assertEqual(preview_length(raw), 140)
        self.assertEqual(check_proposal(raw), check_proposal(filled))
        tmp = tempfile.mkdtemp()
        try:
            _write(os.path.join(tmp, "proposal.md"), raw)
            report = verify_job.verify(tmp)
            self.assertEqual(report.preview_len, 140)
            self.assertTrue(any("counts [N] as 1 char" in n for n in report.notes))
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                verify_job.print_reports([report])
            self.assertIn("note  preview counts [N] as 1 char", buf.getvalue())
        finally:
            shutil.rmtree(tmp)


# --------------------------------------------------------------------------
# Second review round: Loom tokens, in-place log rewrite, stale plain GHL,
# mockups as builds, own-archetype exemption, staged batch copies, url line.
# --------------------------------------------------------------------------

GHL_SPEC = {
    "title": "Your GHL Flow",
    "platform": "gohighlevel",
    "nodes": [
        {"key": "t", "kind": "trigger.app", "app": "ghl", "op": "contact_tag_added",
         "label": "1 - Tag Added", "params": {"tag": "call-booked"}},
        {"key": "a", "kind": "app.action", "app": "ghl", "op": "remove_tag",
         "label": "2 - Clear the Old Tag", "params": {"tag": "call-cancelled"}},
    ],
    "edges": [{"from": "t", "to": "a"}],
}
GHL_SLUG = "your-ghl-flow"
SHARE = "https://www.loom.com/share/"


class TestLoomTokens(TestFinalize):
    """Defect 1: a trailing slash or query string on the Loom URL."""

    def set_proposal(self, link):
        # A proposal already finalized (by hand, or by the old code) with `link`.
        text = make_proposal(140, link=link).replace("[START]", "today")
        _write(os.path.join(self.job, "proposal.md"), text)

    def go(self, loom, *extra):
        return self.run_main("--loom", loom, "--runtime", "1", "--start", "today",
                             "--no-log", *extra)

    def test_rerun_with_trailing_slash_or_sid_is_the_same_video(self):
        code, output = self.go(SHARE + "abc123/")
        self.assertEqual(code, 0, output)
        self.assertIn(SHARE + "abc123\n", self.proposal())  # stored normalized
        text = self.proposal()
        for same in (SHARE + "abc123/", SHARE + "abc123?sid=9f8e7d", SHARE + "abc123"):
            code, output = self.go(same)
            self.assertEqual(code, 0, output)
            self.assertNotIn("REFUSED", output)
            self.assertEqual(self.proposal(), text)

    def test_same_video_already_in_proposal_with_slash_or_sid(self):
        # "//" and a doubled "?sid=" are what the old replace wrote; the new
        # code repairs them, but never accepts them as a --loom value.
        for glued in ("/", "?sid=9f8e7d", "//", "?sid=9f8e7d?sid=9f8e7d"):
            self.set_proposal(SHARE + "abc123" + glued)
            looms = [SHARE + "abc123"]
            if glued in ("/", "?sid=9f8e7d"):
                looms.append(SHARE + "abc123" + glued)
            for loom in looms:
                code, output = self.go(loom)
                self.assertEqual(code, 0, (glued, output))
                text = self.proposal()
                self.assertIn(SHARE + "abc123\n", text, glued)
                self.assertNotIn("sid=", text)
                self.assertNotIn("abc123/", text)
                self.assertEqual(check_proposal(text)[0], [])

    def test_replace_loom_with_the_same_url_does_not_corrupt(self):
        for glued in ("/", "?sid=9f8e7d"):
            self.set_proposal(SHARE + "abc123" + glued)
            code, output = self.go(SHARE + "abc123" + glued, "--replace-loom")
            self.assertEqual(code, 0, output)
            text = self.proposal()
            self.assertNotIn("abc123//", text)
            self.assertNotIn("?sid=9f8e7d?sid", text)
            self.assertIn(SHARE + "abc123\n", text)

    def test_replace_with_a_new_video_drops_the_old_query(self):
        self.set_proposal(SHARE + "abc123?sid=9f8e7d")
        code, output = self.go(SHARE + "zzz999", "--replace-loom")
        self.assertEqual(code, 0, output)
        text = self.proposal()
        self.assertIn(SHARE + "zzz999\n", text)
        self.assertNotIn("sid=", text)
        self.assertNotIn("abc123", text)
        self.assertEqual(check_proposal(text)[0], [])

    def test_existing_loom_takes_the_whole_token(self):
        text = "see " + SHARE + "abc123?sid=9f8e7d.\nand " + SHARE + "abc123/ here"
        self.assertEqual(finalize.existing_loom(text), SHARE + "abc123?sid=9f8e7d")
        self.assertEqual(finalize.set_loom(text, "abc123", SHARE + "new1"),
                         "see " + SHARE + "new1.\nand " + SHARE + "new1 here")

    def test_bad_loom_argument_refused(self):
        original = self.proposal()
        for bad in (SHARE, SHARE + "abc/def", "https://loom.com/share/abc", SHARE + "a b"):
            code, output = self.go(bad)
            self.assertEqual(code, 2, bad)
            self.assertIn("--loom must be a Loom share link", output)
        self.assertEqual(self.proposal(), original)

    def test_verify_link_check_rejects_anything_glued_to_the_id(self):
        ok = check_proposal(make_proposal(link=SHARE + "abc123?sid=9f8e7d"))[0]
        self.assertEqual(ok, [])
        for glued in ("/", "//", "?sid=1?sid=1", "#t=3", ".", "?sid=1/x#y"):
            fails = check_proposal(make_proposal(link=SHARE + "abc123" + glued))[0]
            self.assertTrue(any("link must be" in f for f in fails), (glued, fails))
        # end of text right after the id is fine
        self.assertTrue(verify_job._LOOM_LINK.match(SHARE + "abc123"))


class TestLogRewriteInPlace(TestFinalize):
    """Defect 2: after --replace-loom the logged row follows the proposal,
    in place, every other byte and line ending untouched."""

    URL = "https://www.upwork.com/jobs/~01"

    def build_csv(self, target):
        header = ",".join(finalize.CSV_HEADER)
        other = ("2026-09-01T10:00,Other Job,https://www.upwork.com/jobs/~99,,,n8n,other,4,"
                 "https://www.loom.com/share/other1,standard,140,,,,,,,")
        quoted = ('2026-09-02T11:00,"Job, with comma",https://www.upwork.com/jobs/~98,,,make,'
                  'x,5,https://www.loom.com/share/q1,standard,141,,,,,,,"note ""one""\r\nline two"')
        return (header + "\n" + other + "\r\n" + target + "\r\n" + quoted + "\n"
                + other.replace("~99", "~97"))  # last line has no terminator

    def test_replace_rewrites_the_row_in_place(self):
        code, output = self.run_main("--loom", SHARE + "abc123", "--runtime", "1",
                                     "--start", "today", "--no-log")
        self.assertEqual(code, 0, output)
        target = ('2026-09-22T09:00,CRM Sync Job,{},,,n8n,your-lead-router,3,'
                  '{}abc123,standard,140,,"yes",,,,,"hand note, kept"').format(self.URL, SHARE)
        original = self.build_csv(target)
        with open(self.csv, "w", encoding="utf-8", newline="") as fh:
            fh.write(original)

        code, output = self.run_main("--loom", SHARE + "zzz999?sid=1", "--runtime", "3",
                                     "--start", "today", "--replace-loom", "--name", "Dana")
        self.assertEqual(code, 0, output)
        self.assertNotIn("--relog", output)
        self.assertIn("in place on 1 existing row(s)", output)
        with open(self.csv, "rb") as fh:
            after = fh.read().decode("utf-8")
        # "Hey Dana" is one char shorter than "Hey there": 139.
        expected = original.replace(
            target, target.replace(SHARE + "abc123,standard,140,",
                                   SHARE + "zzz999,standard,139,"))
        self.assertNotEqual(expected, original)
        self.assertEqual(after, expected)
        rows = finalize.logged_rows(self.csv, self.URL)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["loom_url"], SHARE + "zzz999")
        self.assertEqual(rows[0]["opener_visible_chars"], "139")
        self.assertEqual(rows[0]["notes"], "hand note, kept")
        self.assertIn(SHARE + "zzz999\n", self.proposal())

    def test_unsplittable_log_refuses_and_writes_nothing(self):
        self.run_main("--loom", SHARE + "abc123", "--runtime", "1", "--start", "today",
                      "--no-log")
        proposal = self.proposal()
        bad = ",".join(h for h in finalize.CSV_HEADER if h != "opener_visible_chars")
        bad += "\n2026-09-22T09:00,T,{},x\n".format(self.URL)
        with open(self.csv, "w", encoding="utf-8", newline="") as fh:
            fh.write(bad)
        code, output = self.run_main("--loom", SHARE + "zzz999", "--runtime", "3",
                                     "--start", "today", "--replace-loom")
        self.assertEqual(code, 2, output)
        self.assertIn("cannot update the logged row", output)
        self.assertEqual(self.proposal(), proposal)
        with open(self.csv, encoding="utf-8", newline="") as fh:
            self.assertEqual(fh.read(), bad)

    def test_rewrite_logged_keeps_everything_else(self):
        text = ('a,job_url,loom_url,opener_visible_chars\r\n'
                '"x\ny",u1,"old",140\r\n'
                'z,u2,keep,150\n'
                ' q ,u1,old2,1')
        out, n = finalize.rewrite_logged(text, "u1", {"loom_url": "new, url",
                                                      "opener_visible_chars": "133"})
        self.assertEqual(n, 2)
        self.assertEqual(out, 'a,job_url,loom_url,opener_visible_chars\r\n'
                              '"x\ny",u1,"new, url",133\r\n'
                              'z,u2,keep,150\n'
                              ' q ,u1,"new, url",133')

    def test_no_url_line_refuses_to_log(self):
        _write(os.path.join(self.job, "jd.txt"), "CRM Sync Job\nmeta\n\npost\n")
        original = self.proposal()
        with open(self.csv, encoding="utf-8") as fh:
            before = fh.read()
        for _ in range(2):
            code, output = self.run_main("--loom", SHARE + "abc123", "--runtime", "1",
                                         "--start", "today")
            self.assertEqual(code, 2, output)
            self.assertIn("no 'url: <upwork job url>' line", output)
        self.assertEqual(self.proposal(), original)
        with open(self.csv, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), before)
        code, output = self.run_main("--loom", SHARE + "abc123", "--runtime", "1",
                                     "--start", "today", "--no-log")
        self.assertEqual(code, 0, output)


class TestStalePlainGhl(TestGhlSplitCli):
    """Defect 3: an old plain <slug>.ghl.json next to a fresh split set."""

    def clip_aged(self, fresh, aged):
        from upwork_gen import cli
        for name, body in list(fresh.items()) + list(aged.items()):
            _write(os.path.join(self.tmp, name), body)
        hour_ago = os.path.getmtime(os.path.join(self.tmp, list((fresh or aged).keys())[0])) - 3600
        for name in aged:
            os.utime(os.path.join(self.tmp, name), (hour_ago, hour_ago))
        dsl = os.path.join(self.tmp, "s.excalidraw.dsl")
        _write(dsl, "x")
        copied = []
        buf = io.StringIO()
        with unittest.mock.patch.object(cli, "OUT_DIR", self.tmp), \
                unittest.mock.patch.object(cli, "latest_run_dsl", lambda: dsl), \
                unittest.mock.patch.object(cli, "clip_copy",
                                           lambda text: copied.append(text) or True), \
                contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            code = cli.main(["clip", "ghl"])
        return code, buf.getvalue(), copied

    def test_hour_old_plain_file_loses_to_fresh_split_files(self):
        code, output, copied = self.clip_aged(
            {"s--2-booked.ghl.json": "TWO", "s--1-form.ghl.json": "ONE"},
            {"s.ghl.json": "OLD PLAIN", "s--3-gone.ghl.json": "OLD PART"})
        self.assertEqual(code, 0, output)
        self.assertEqual(copied, ["ONE"])
        self.assertIn("2 GHL workflows", output)
        self.assertIn(os.path.join(self.tmp, "s--1-form.ghl.json"), output)
        self.assertIn(os.path.join(self.tmp, "s--2-booked.ghl.json"), output)
        self.assertNotIn(os.path.join(self.tmp, "s--3-gone.ghl.json"), output)
        self.assertIn("ignored (older runs of this title): s.ghl.json, s--3-gone.ghl.json",
                      output)

    def test_old_split_files_lose_to_a_fresh_plain_file(self):
        code, output, copied = self.clip_aged(
            {"s.ghl.json": "PLAIN"}, {"s--1-form.ghl.json": "OLD ONE"})
        self.assertEqual(code, 0, output)
        self.assertEqual(copied, ["PLAIN"])
        self.assertNotIn("GHL workflows", output)

    def test_only_old_ghl_files_is_refused(self):
        code, output, copied = self.clip_aged({}, {"s.ghl.json": "OLD PLAIN"})
        self.assertEqual(code, 2, output)
        self.assertEqual(copied, [])
        self.assertIn("produced no .ghl.json", output)
        self.assertIn("not handed over: s.ghl.json", output)


class TestGhlCoexistenceVerify(unittest.TestCase):
    """Defect 3, verify half."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_plain_and_split_ghl_for_one_slug_fail(self):
        job = make_job(self.tmp, "j", spec=GHL_SPEC)
        _write(os.path.join(job, GHL_SLUG + ".excalidraw"), "{}")
        _write(os.path.join(job, GHL_SLUG + "--1-form.ghl.json"), "{}")
        _write(os.path.join(job, GHL_SLUG + "--2-booked.ghl.json"), "{}")
        both = lambda: [f for f in verify_job.verify(job).fails  # noqa: E731
                        if "both as one workflow" in f]
        self.assertEqual(both(), [])
        _write(os.path.join(job, GHL_SLUG + ".ghl.json"), "{}")
        hits = both()
        self.assertEqual(len(hits), 1, hits)
        self.assertIn(GHL_SLUG + ".ghl.json", hits[0])
        self.assertIn(GHL_SLUG + "--2-booked.ghl.json", hits[0])
        os.remove(os.path.join(job, GHL_SLUG + ".ghl.json"))
        _write(os.path.join(job, GHL_SLUG + ".ghl-prompt.txt"), "x")  # any GHL suffix
        self.assertEqual(len(both()), 1)
        # the mockup is always plain, even for a split spec
        os.remove(os.path.join(job, GHL_SLUG + ".ghl-prompt.txt"))
        _write(os.path.join(job, GHL_SLUG + ".ghl.html"), "<html>")
        self.assertEqual(both(), [])


class TestLoaderGhlConflict(TestJobLoader):
    """Defect 3, loader half: refuse instead of loading the plain file."""

    def test_plain_next_to_split_is_refused(self):
        spec = dict(N8N_SPEC, title="Your GHL Flow")
        _write(os.path.join(self.job, "spec.json"), json.dumps(spec))
        for name, body in (("your-ghl-flow.ghl.json", "OLD PLAIN"),
                           ("your-ghl-flow--1-form.ghl.json", "ONE"),
                           ("your-ghl-flow--2-booked.ghl.json", "TWO")):
            _write(os.path.join(self.job, name), body)
        for args in (("my-job",), ("my-job", "ghl")):
            code, output = self.run_job(*args)
            self.assertEqual(code, 1, output)
            self.assertIn("REFUSED", output)
            self.assertIn("verify_job", output)
            self.assertFalse(os.path.exists(self.clip), output)
            self.assertFalse(os.path.exists(self.imports) and os.listdir(self.imports))

    def test_plain_alone_still_loads(self):
        spec = dict(N8N_SPEC, title="Your GHL Flow")
        _write(os.path.join(self.job, "spec.json"), json.dumps(spec))
        _write(os.path.join(self.job, "your-ghl-flow.ghl.json"), "PLAIN")
        code, output = self.run_job("my-job")
        self.assertEqual(code, 0, output)
        self.assertEqual(_read(self.clip), "PLAIN")
        self.assertEqual(os.listdir(self.imports), ["your-ghl-flow.ghl.json"])


class TestMockupIsABuild(BatchCase):
    """Defect 4: <slug>.ghl.html / .zapier.html are copied, retired, checked."""

    def test_batch_copies_the_mockup_and_retires_an_old_titles(self):
        job = make_job(self.tmp, "ghl-job", spec=GHL_SPEC)
        _write(os.path.join(job, "old-title.ghl.html"), "OLD MOCKUP")
        _write(os.path.join(job, "old-title.zapier.html"), "OLD ZAP")
        _write(os.path.join(job, GHL_SLUG + ".ghl.html"), "PREVIOUS RUN")
        code, output = self.batch(job)
        names = os.listdir(job)
        self.assertIn(GHL_SLUG + ".ghl.html", names, output)
        self.assertNotEqual(_read(os.path.join(job, GHL_SLUG + ".ghl.html")), "PREVIOUS RUN")
        self.assertIn(GHL_SLUG + ".ghl.json", names)
        self.assertNotIn("old-title.ghl.html", names)
        stale = os.listdir(os.path.join(job, ".stale"))
        self.assertIn("old-title.ghl.html", stale)
        self.assertIn("old-title.zapier.html", stale)
        self.assertIn(GHL_SLUG + ".ghl.html", output)  # listed under "copied into job"
        report = verify_job.verify(job)
        self.assertFalse(any("not from the current spec" in f for f in report.fails),
                         report.fails)

    def test_verify_flags_an_older_titles_mockup(self):
        job = make_job(self.tmp, "j", spec=GHL_SPEC)
        for suffix in (".ghl.html", ".zapier.html"):
            _write(os.path.join(job, "old-title" + suffix), "<html>")
            hits = [f for f in verify_job.verify(job).fails if "not from the current spec" in f]
            self.assertEqual(len(hits), 1)
            self.assertIn("old-title" + suffix, hits[0])
            os.remove(os.path.join(job, "old-title" + suffix))
        self.assertTrue(verify_job.is_current_build(GHL_SLUG + ".ghl.html", GHL_SLUG))
        self.assertEqual(verify_job.build_suffix("x.zapier.html"), ".zapier.html")

    def test_failed_copy_leaves_the_old_set_intact(self):
        job = make_job(self.tmp, "j")
        self.batch(job)  # a clean first build
        before = {n: _read(os.path.join(job, n)) for n in os.listdir(job)
                  if os.path.isfile(os.path.join(job, n))}
        _write(os.path.join(job, "old-title.n8n.json"), "OLD")
        before["old-title.n8n.json"] = "OLD"
        real = shutil.copyfile
        calls = []

        def flaky(src, dst, *a, **k):
            calls.append(dst)
            if len(calls) == 2:
                raise OSError("disk full")
            return real(src, dst, *a, **k)

        with unittest.mock.patch.object(shutil, "copyfile", flaky):
            code, output = self.batch(job)
        self.assertEqual(code, 1, output)
        self.assertIn("disk full", output)
        self.assertIn(os.sep + ".batch-", calls[1])  # it failed in the staging copy
        after = {n: _read(os.path.join(job, n)) for n in os.listdir(job)
                 if os.path.isfile(os.path.join(job, n))}
        self.assertEqual(after, before)  # nothing swapped, nothing retired
        self.assertEqual([n for n in os.listdir(job) if n.startswith(".")], [])


class TestOwnArchetypeExemption(unittest.TestCase):
    """Defect 5: a rebuild under a new title is not a clone of its own
    earlier archetype; another job's archetype still warns."""

    LABELS = ["Count the list", "Verify every address", "Buy lookalike domains",
              "Publish SPF DKIM DMARC", "Import mailboxes into Instantly",
              "Warm up for two weeks"]

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.vault = os.path.join(self.tmp, "vault", "archetypes")
        self.sources = os.path.join(self.tmp, "vault", "sources")
        os.makedirs(self.vault)
        os.makedirs(self.sources)
        spec = {"title": "Your Meeting Engine Rebuilt", "platform": "diagram",
                "nodes": [{"key": "n{}".format(i), "kind": "data.transform",
                           "label": "{} - {}".format(i + 1, label)}
                          for i, label in enumerate(self.LABELS)]}
        self.job = make_job(self.tmp, "cold-email-job", spec=spec)
        _write(os.path.join(self.job, GHL_SLUG + ".excalidraw"), "{}")
        self.url = "https://www.upwork.com/jobs/~cold-email-job"

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def archetype(self, archetype_id, title, source=None):
        nodes = [{"key": "n{}".format(i), "kind": "data.transform",
                  "label": "{} - {}".format(i + 1, label)} for i, label in enumerate(self.LABELS)]
        _write(os.path.join(self.vault, archetype_id + ".json"),
               json.dumps({"title": title, "platform": "diagram", "nodes": nodes}))
        if source is not None:
            _write(os.path.join(self.sources, archetype_id + ".txt"), source)

    def lint(self):
        report = verify_job.verify(self.job, vault_dir=self.vault)
        return ([w for w in report.warns if "chart overlaps" in w],
                [n for n in report.notes if "chart overlaps" in n])

    def test_old_archetype_from_this_jobs_posting_is_exempt(self):
        self.archetype("your_meeting_engine_first_cut", "Your Meeting Engine First Cut",
                       "url: {}\nTitle\n\npost\n".format(self.url))
        self.archetype("someone_elses_engine", "Someone Else's Engine",
                       "url: https://www.upwork.com/jobs/~other\nOther\n\npost\n")
        warns, notes = self.lint()
        self.assertEqual(warns, ["lint: chart overlaps someone_elses_engine on 6 of 6 steps"])
        self.assertEqual(len(notes), 1, notes)
        self.assertIn("your_meeting_engine_first_cut", notes[0])
        self.assertIn("own earlier build", notes[0])

    def test_old_title_in_stale_is_exempt(self):
        self.archetype("your_meeting_engine_first_cut", "Your Meeting Engine First Cut")
        warns, _ = self.lint()
        self.assertEqual(len(warns), 1)  # no source, no .stale/: still a warning
        _write(os.path.join(self.job, ".stale",
                            "20260922-101500.your-meeting-engine-first-cut.excalidraw"), "{}")
        warns, notes = self.lint()
        self.assertEqual(warns, [])
        self.assertIn(".stale/", notes[0])
        self.assertEqual(verify_job.stale_slugs(self.job), ["your-meeting-engine-first-cut"])

    def test_archetype_named_in_spec_needs_evidence(self):
        # Third review, should-fix B: the `archetype` key alone is no evidence.
        self.archetype("pinned_id", "Some Older Title")
        with open(os.path.join(self.job, "spec.json"), encoding="utf-8") as fh:
            spec = json.load(fh)
        spec["archetype"] = "pinned_id"
        _write(os.path.join(self.job, "spec.json"), json.dumps(spec))
        warns, notes = self.lint()
        self.assertEqual(warns, ["lint: chart overlaps pinned_id on 6 of 6 steps"])
        self.assertEqual(notes, [])
        # With this job's posting archived for it, it is the job's own build.
        _write(os.path.join(self.sources, "pinned_id.txt"),
               "url: {}\nTitle\n\npost\n".format(self.url))
        warns, notes = self.lint()
        self.assertEqual(warns, [])
        self.assertIn("named in spec.json; learned from this job's jd.txt", notes[0])
        # So it is with its title's builds retired into .stale/.
        os.remove(os.path.join(self.sources, "pinned_id.txt"))
        _write(os.path.join(self.job, ".stale", "some-older-title.excalidraw"), "{}")
        warns, notes = self.lint()
        self.assertEqual(warns, [])
        self.assertIn("named in spec.json; its title's builds are in .stale/", notes[0])

    def test_spec_copied_from_another_jobs_vault_file_still_warns(self):
        # learn.py writes the archetype id (plus `learned`, `learned_at`) into
        # the vault file, so a spec copied from it carries that id along.
        other = "someone_elses_engine"
        vault_file = os.path.join(self.vault, other + ".json")
        self.archetype(other, "Someone Else's Engine",
                       "url: https://www.upwork.com/jobs/~other\nOther\n\npost\n")
        with open(vault_file, encoding="utf-8") as fh:
            learned = json.load(fh)
        learned.update({"archetype": other, "learned": True, "learned_at": "2026-09-01"})
        _write(vault_file, json.dumps(learned))
        spec_path = os.path.join(self.job, "spec.json")
        for retitle in (None, "Your Meeting Engine For Dana"):
            if retitle is None:
                shutil.copyfile(vault_file, spec_path)  # verbatim: same id, same title
            else:
                _write(spec_path, json.dumps(dict(learned, title=retitle)))
            warns, notes = self.lint()
            self.assertEqual(warns, ["lint: chart overlaps {} on 6 of 6 steps".format(other)],
                             retitle)
            self.assertEqual(notes, [], retitle)
        # The same copy is the job's own build once the evidence says so.
        _write(os.path.join(self.sources, other + ".txt"),
               "url: {}\nTitle\n\npost\n".format(self.url))
        warns, notes = self.lint()
        self.assertEqual(warns, [])
        self.assertIn("named in spec.json; learned from this job's jd.txt", notes[0])

    def test_stale_slugs_reads_split_and_stamped_names(self):
        for name in ("a-title.n8n.json", "20260101-000000.b-title.excalidraw",
                     "20260101-000000.2.c-title--1-form.ghl.json", "notes.md"):
            _write(os.path.join(self.job, ".stale", name), "x")
        self.assertEqual(verify_job.stale_slugs(self.job), ["a-title", "b-title", "c-title"])


# --------------------------------------------------------------------------
# Third review round: the in-place log edit reads quotes the way csv does and
# must reach exactly the rows csv reads; a same-video runtime correction; the
# spec's `archetype` key needs evidence.
# --------------------------------------------------------------------------


def _quote_toggling_split_records(text):
    """finalize._split_records before the fix: every `"` toggled "quoted", so
    a bare `55"` in one row merged the rows after it."""
    out, start, i, quoted, n = [], 0, 0, False, len(text)
    while i < n:
        char = text[i]
        if char == '"':
            quoted = not quoted
        elif not quoted and char in "\r\n":
            term = "\r\n" if text.startswith("\r\n", i) else char
            out.append((text[start:i], term))
            i += len(term)
            start = i
            continue
        i += 1
    if start < n:
        out.append((text[start:], ""))
    return out


def _csv_rows(text):
    return list(csv.reader(io.StringIO(text, newline="")))


def _refused_and_untouched(case, run):
    """Run finalize via `run`; assert exit 2 and that proposal.md and the log
    are byte-identical afterwards, with no temp file left beside either."""
    with open(case.csv, "rb") as fh:
        log_before = fh.read()
    with open(os.path.join(case.job, "proposal.md"), "rb") as fh:
        proposal_before = fh.read()
    listing = (sorted(os.listdir(case.job)), sorted(os.listdir(case.tmp)))
    code, output = run()
    case.assertEqual(code, 2, output)
    case.assertIn("REFUSED", output)
    case.assertIn("nothing written", output)
    case.assertNotIn("wrote:", output)
    with open(case.csv, "rb") as fh:
        case.assertEqual(fh.read(), log_before)
    with open(os.path.join(case.job, "proposal.md"), "rb") as fh:
        case.assertEqual(fh.read(), proposal_before)
    case.assertEqual((sorted(os.listdir(case.job)), sorted(os.listdir(case.tmp))), listing)
    return output


class TestCsvQuoteRules(unittest.TestCase):
    """_split_records/_split_fields cut exactly where csv.reader does."""

    def check(self, text):
        records = finalize._split_records(text)
        self.assertEqual("".join(r + t for r, t in records), text)
        mine = [(_csv_rows(r) or [[]])[0] for r, _ in records]
        self.assertEqual(mine, _csv_rows(text), repr(text))
        for record, _ in records:
            if not record:
                continue
            fields = finalize._split_fields(record)
            self.assertEqual(",".join(fields), record)
            values = []
            for raw in fields:
                rows = _csv_rows(raw)  # one field alone: one row of at most one value
                self.assertLessEqual(len(rows), 1, repr(raw))
                self.assertLessEqual(len(rows[0]) if rows else 0, 1, repr(raw))
                values.append(rows[0][0] if rows and rows[0] else "")
            self.assertEqual(values, _csv_rows(record)[0], repr(record))

    def test_quotes_count_only_at_the_start_of_a_field(self):
        for text in (
            'a,55" monitor\nb,c\n',          # the reviewer's bare quote: a character
            'a,55" and 65"\nb,"x,y"\n',       # an even count in one row
            'a,5"\nb,c\nd,6"\ne\n',           # one in each of two rows around another
            'a,"say ""hi"", ok"\r\nb\n',      # "" inside a quoted field
            '"x\ny",1\r\n"p\rq",2\rz',        # line breaks inside quotes; \r ends a row
            'a,"ab"cd,e\n',                   # text after the closing quote runs on
            ' "sp",1\n',                      # a space first: the quote is a character
            'a,"open\nb,c',                   # a quote left open runs to the end
            '\n\r\n\r',                       # blank rows
        ):
            self.check(text)

    def test_agrees_with_csv_reader_on_random_text(self):
        import random
        rng = random.Random(20260922)
        alphabet = ["a", "b", ",", '"', '"', "\n", "\r", " "]
        for _ in range(3000):
            self.check("".join(rng.choice(alphabet) for _ in range(rng.randint(0, 24))))

    def test_rewrite_keeps_line_endings_and_quoted_fields_around_bare_quotes(self):
        text = ('a,job_url,loom_url,opener_visible_chars,notes\r\n'
                'x,u0,l0,1,55" tv\r\n'
                '"m\r\nl",u1,old,140,"q ""x"", y"\n'
                'y,u2,keep,150,6" gap\r'
                'z,u1,old2,2,tail " q')
        out, n = finalize.rewrite_logged(text, "u1", {"loom_url": "new",
                                                      "opener_visible_chars": "133"})
        self.assertEqual(n, 2)
        self.assertEqual(out, text.replace("old,140", "new,133").replace("old2,2", "new,133"))


class TestLogRewriteQuotes(TestFinalize):
    """Blocking defect: a hand-typed `55"` in an earlier row made the in-place
    edit match nothing while finalize still reported success."""

    URL = "https://www.upwork.com/jobs/~01"
    OLD, NEW = SHARE + "aaa111", SHARE + "bbb222"
    MONITOR = ("2026-09-22T08:00,Monitor Job,https://www.upwork.com/jobs/~022222222222222222222,"
               ",,n8n,monitor,4,https://www.loom.com/share/mmm000,standard,140,,,,,,,"
               'client has a 55" monitor')

    def setUp(self):
        super().setUp()
        with open(self.csv, encoding="utf-8", newline="") as fh:
            self.base = fh.read()  # the copy of the real log

    def target(self, title="CRM Sync Job", notes="", loom=None, chars="140"):
        return ("2026-09-22T09:00,{},{},,,n8n,your-lead-router,3,{},standard,{},,,,,,,{}"
                .format(title, self.URL, loom or self.OLD, chars, notes))

    def reset(self, *rows):
        """Proposal finalized with the old video; the real log plus `rows`."""
        _write(os.path.join(self.job, "proposal.md"),
               make_proposal(140, link=self.OLD).replace("[START]", "today"))
        text = self.base + "".join(row + "\n" for row in rows)
        with open(self.csv, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        return text

    def log(self):
        with open(self.csv, encoding="utf-8", newline="") as fh:
            return fh.read()

    def replace(self, runtime="2"):
        return self.run_main("--loom", self.NEW, "--replace-loom", "--runtime", runtime,
                             "--start", "today")

    def test_bare_quote_in_an_earlier_row(self):
        # The reviewer's repro: one `"` (an odd count) in the row before.
        target = self.target()
        original = self.reset(self.MONITOR, target)
        code, output = self.replace()
        self.assertEqual(code, 0, output)
        self.assertIn("updated loom_url and opener_visible_chars in place on 1 existing row(s)",
                      output)
        # "2-min" is as long as "1-min": the count stays 140, the link changes.
        self.assertEqual(self.log(), original.replace(target, self.target(loom=self.NEW)))
        self.assertEqual([r["loom_url"] for r in finalize.logged_rows(self.csv, self.URL)],
                         [self.NEW])
        self.assertIn(self.NEW + "\n", self.proposal())

    def test_even_quote_counts(self):
        two_in_one_row = self.MONITOR.replace('55" monitor', '55" and 65" monitors')
        after = self.MONITOR.replace("~0222", "~0333").replace('55"', '65"')
        for rows in ((two_in_one_row, "TARGET"), (self.MONITOR, "TARGET", after)):
            target = self.target()
            original = self.reset(*[target if r == "TARGET" else r for r in rows])
            code, output = self.replace("12")  # "12-min": the preview is 141
            self.assertEqual(code, 0, output)
            self.assertIn("in place on 1 existing row(s)", output)
            self.assertEqual(self.log(), original.replace(
                target, self.target(loom=self.NEW, chars="141")), rows)

    def test_stray_quote_in_the_target_row(self):
        after = self.MONITOR.replace("~0222", "~0444").replace('client has a 55" monitor', "x")
        for title, notes in (('Mount a 55" TV', 'client said 6" gap'),
                             ("CRM Sync Job", '"said ""ok"", 55"" wide"'),
                             ('"Quoted, title"', 'tail " quote')):
            target = self.target(title=title, notes=notes)
            original = self.reset(target, after)
            code, output = self.replace("12")
            self.assertEqual(code, 0, (title, output))
            self.assertIn("in place on 1 existing row(s)", output)
            self.assertEqual(self.log(), original.replace(target, self.target(
                title=title, notes=notes, loom=self.NEW, chars="141")), title)
            row = finalize.logged_rows(self.csv, self.URL)[0]
            self.assertEqual((row["loom_url"], row["opener_visible_chars"]), (self.NEW, "141"))
            self.assertEqual([row["job_title"], row["notes"]],
                             [_csv_rows(title)[0][0], _csv_rows(notes)[0][0]])

    def test_edit_that_misses_the_row_refuses_before_writing(self):
        # The pre-fix splitter merges everything after the `55"`: csv still
        # reads the target row, the edit matches none. Nothing is written.
        self.reset(self.MONITOR, self.target())
        with unittest.mock.patch.object(finalize, "_split_records",
                                        _quote_toggling_split_records):
            output = _refused_and_untouched(self, self.replace)
        line = self.base.count("\n") + 2  # the monitor row, then the target
        self.assertIn("1 row(s) for {} (line {}, applied_at 2026-09-22T09:00) but the in-place "
                      "edit matched 0".format(self.URL, line), output)
        self.assertIn("Set loom_url {} and opener_visible_chars 140 on that row by hand"
                      .format(self.NEW), output)

    def test_csv_and_edit_disagreeing_without_a_mock_refuses(self):
        # Two job_url columns: csv.DictReader keeps the last, the edit uses
        # the first. A real disagreement, so the count check must catch it.
        _write(os.path.join(self.job, "proposal.md"),
               make_proposal(140, link=self.OLD).replace("[START]", "today"))
        with open(self.csv, "w", encoding="utf-8", newline="") as fh:
            fh.write(",".join(finalize.CSV_HEADER + ["job_url"]) + "\n"
                     + self.target().replace(self.URL, "") + "," + self.URL + "\n")
        output = _refused_and_untouched(self, self.replace)
        self.assertIn("(line 2, applied_at 2026-09-22T09:00) but the in-place edit matched 0",
                      output)


class TestRuntimeCorrection(TestFinalize):
    """Should-fix A: the same video re-run with a corrected --runtime updates
    the preview's `<n>-min`, the count, and the logged row in place."""

    URL = "https://www.upwork.com/jobs/~01"
    LOOM = SHARE + "abc123"

    def first_run(self):
        """Fill the proposal with a 1-min Loom and log it; the log's text."""
        _write(os.path.join(self.job, "proposal.md"),
               make_proposal(140).replace("1-min", "[N]-min")
               + "\nHappy to hop on a 30-min call.\n")
        code, output = self.run_main("--loom", self.LOOM, "--runtime", "1", "--start", "today",
                                     "--draft", "Friday")
        self.assertEqual(code, 0, output)
        self.assertIn("logged:", output)
        return self.log()

    def log(self):
        with open(self.csv, encoding="utf-8", newline="") as fh:
            return fh.read()

    def rerun(self, runtime, *extra, loom=None):
        return self.run_main("--loom", loom or self.LOOM, "--runtime", runtime,
                             "--start", "today", *extra)

    def test_new_runtime_updates_the_token_the_count_and_the_row(self):
        before = self.first_run()
        row = before.splitlines(True)[-1]  # the row the first run appended
        self.assertIn(",standard,140,", row)
        code, output = self.rerun("12")
        self.assertEqual(code, 0, output)
        text = self.proposal()
        self.assertIn("12-min video", text)
        self.assertNotIn("1-min video", text)
        self.assertIn("30-min call", text)  # the body is not the runtime
        self.assertIn("runtime: 1-min -> 12-min in the preview", output)
        self.assertIn("preview (141 chars)", output)
        self.assertIn("updated opener_visible_chars in place on 1 existing row(s)", output)
        self.assertNotIn("--relog", output)
        # Only that field of that row changes; loom_url and every other byte stay.
        self.assertEqual(self.log(), before[:-len(row)]
                         + row.replace(",standard,140,", ",standard,141,"))

        # With --replace-loom (and a share-dialog query) it is the same video.
        code, output = self.rerun("3", "--replace-loom", loom=self.LOOM + "?sid=9f8e7d")
        self.assertEqual(code, 0, output)
        self.assertIn("3-min video", self.proposal())
        self.assertIn("runtime: 12-min -> 3-min in the preview", output)
        self.assertIn("preview (140 chars)", output)
        self.assertEqual(self.log(), before)

        # The same runtime again changes nothing and logs nothing.
        proposal = self.proposal()
        code, output = self.rerun("3")
        self.assertEqual(code, 0, output)
        self.assertNotIn("runtime:", output)
        self.assertIn("NOT LOGGED", output)
        self.assertEqual(self.proposal(), proposal)
        self.assertEqual(self.log(), before)

    def test_same_length_runtime_leaves_the_log_file_alone(self):
        before = self.first_run()
        inode = os.stat(self.csv).st_ino
        code, output = self.rerun("3")  # "3-min" is as long as "1-min"
        self.assertEqual(code, 0, output)
        self.assertIn("3-min video", self.proposal())
        self.assertIn("opener_visible_chars already current on 1 existing row(s)", output)
        self.assertEqual(self.log(), before)
        self.assertEqual(os.stat(self.csv).st_ino, inode)  # not rewritten

    def test_several_runtime_tokens_are_never_guessed(self):
        # A hand-written "15-min" in the opener: re-runs never rewrite it.
        _write(os.path.join(self.job, "proposal.md"),
               make_proposal(133).replace("I x", "I 15-min x", 1))
        code, output = self.rerun("1")
        self.assertEqual(code, 0, output)
        proposal, before = self.proposal(), self.log()
        self.assertIn("15-min", proposal)
        # Warned every time, even when --runtime equals one of the tokens:
        # which one is the Loom runtime is still a guess.
        for runtime in ("1", "2", "15"):
            code, output = self.rerun(runtime)
            self.assertEqual(code, 0, output)
            self.assertEqual(self.proposal(), proposal, runtime)
            self.assertEqual(self.log(), before, runtime)
            self.assertNotIn("runtime:", output)
            self.assertIn("NOT LOGGED", output)
            self.assertIn("several <n>-min tokens (15-min, 1-min), so --runtime {} was not "
                          "applied".format(runtime), output)

    def test_runtime_change_refuses_when_the_edit_misses_the_row(self):
        # The same count check as --replace-loom: a `55"` row just before ours
        # and the pre-fix splitter, so the edit cannot reach the row.
        text = self.first_run()
        row = text.splitlines(True)[-1]
        with open(self.csv, "w", encoding="utf-8", newline="") as fh:
            fh.write(text[:-len(row)] + TestLogRewriteQuotes.MONITOR + "\n" + row)
        with unittest.mock.patch.object(finalize, "_split_records",
                                        _quote_toggling_split_records):
            output = _refused_and_untouched(self, lambda: self.rerun("12"))
        self.assertIn("but the in-place edit matched 0", output)
        self.assertIn("Set opener_visible_chars 141 on that row by hand", output)



class TestFollowUpFixes(TestFinalize):
    """Follow-ups: a real Calendly trigger, a re-run --name, the log row built
    before any write, and --replace-loom with several <n>-min tokens."""

    URL = "https://www.upwork.com/jobs/~01"
    LOOM = SHARE + "abc123"

    def log(self):
        with open(self.csv, encoding="utf-8", newline="") as fh:
            return fh.read()

    def first_run(self, proposal=None):
        _write(os.path.join(self.job, "proposal.md"),
               proposal or make_proposal(140).replace("1-min", "[N]-min"))
        code, output = self.run_main("--loom", self.LOOM, "--runtime", "1", "--start", "today",
                                     "--draft", "Friday")
        self.assertEqual(code, 0, output)
        self.assertIn("logged:", output)
        return self.log()

    def test_real_calendly_trigger_passes_unmapped_one_fails(self):
        def spec(app):
            return WorkflowSpec.from_dict({
                "title": "Your Flow", "platform": "n8n",
                "nodes": [{"key": "t", "kind": "trigger.app", "app": app, "op": "invitee",
                           "label": "1 - Call Booked"},
                          {"key": "s", "kind": "app.action", "app": "slack", "op": "post",
                           "label": "2 - Tell Sales"}],
                "edges": [{"from": "t", "to": "s"}]})

        nodes = [_node("1 - Call Booked", "n8n-nodes-base.calendlyTrigger"),
                 _node("2 - Tell Sales", "n8n-nodes-base.slack")]
        wf = {"name": "Your Flow", "nodes": nodes,
              "connections": {"1 - Call Booked": {"main": [[{"node": "2 - Tell Sales"}]]}},
              "pinData": {n["name"]: [{"json": {}}] for n in nodes}}
        raw = json.dumps(wf)
        real = verify_job.calendly_spec_triggers(spec("calendly"))
        self.assertEqual(real, 1)
        self.assertEqual(check_n8n(wf, raw, "Your Flow", "x", real), [])
        unmapped = verify_job.calendly_spec_triggers(spec("typeform"))
        self.assertEqual(unmapped, 0)
        self.assertTrue(any("calendlyTrigger" in f
                            for f in check_n8n(wf, raw, "Your Flow", "x", unmapped)))
        # A second calendlyTrigger beyond the one real Calendly spec node fails.
        two = dict(wf, nodes=nodes + [_node("3 - Extra", "n8n-nodes-base.calendlyTrigger")])
        self.assertTrue(any("calendlyTrigger" in f
                            for f in check_n8n(two, json.dumps(two), "Your Flow", "x", real)))

    def test_rerun_with_only_name_updates_the_logged_count(self):
        before = self.first_run()
        row = before.splitlines(True)[-1]
        self.assertIn(",standard,140,", row)
        code, output = self.run_main("--loom", self.LOOM, "--runtime", "1",
                                     "--start", "today", "--name", "Dana")
        self.assertEqual(code, 0, output)
        self.assertTrue(self.proposal().startswith("Hey Dana"))
        self.assertIn("preview (139 chars)", output)
        self.assertIn("updated opener_visible_chars in place on 1 existing row(s)", output)
        self.assertNotIn("NOT LOGGED", output)
        self.assertEqual(self.log(), before[:-len(row)]
                         + row.replace(",standard,140,", ",standard,139,"))

    def test_broken_spec_writes_nothing(self):
        spec_path = os.path.join(self.job, "spec.json")
        for label, breaker in (("bad json", lambda: _write(spec_path, "{not json")),
                               ("unreadable", lambda: os.chmod(spec_path, 0))):
            with self.subTest(label):
                breaker()
                try:
                    output = _refused_and_untouched(self, lambda: self.run_main(
                        "--loom", self.LOOM, "--runtime", "1", "--start", "today"))
                finally:
                    os.chmod(spec_path, 0o644)
                self.assertIn("cannot build the log row", output)

    def test_replace_loom_with_several_runtime_tokens_leaves_them(self):
        self.first_run(make_proposal(133).replace("I x", "I 15-min x", 1)
                       .replace("1-min", "[N]-min"))
        proposal = self.proposal()
        self.assertIn("15-min", proposal)
        self.assertIn("1-min video", proposal)
        code, output = self.run_main("--loom", SHARE + "zzz999", "--runtime", "3",
                                     "--start", "today", "--replace-loom")
        self.assertEqual(code, 0, output)
        self.assertIn("several <n>-min tokens (15-min, 1-min), so --runtime 3 was not "
                      "applied", output)
        self.assertEqual(self.proposal(),
                         proposal.replace(self.LOOM, SHARE + "zzz999"))


class TestNameAndRuntimeFollowUps(TestFollowUpFixes):
    """A blank --name never touches the greeting and the log follows every
    re-run that moves the preview; the runtime warnings on the replace and
    retime paths; verify counts Calendly triggers the compiler's way."""

    def assert_row_count(self, text, count):
        self.assertIn(",standard,{},".format(count), text.splitlines(True)[-1])

    def test_blank_name_on_first_run_keeps_the_greeting(self):
        _write(os.path.join(self.job, "proposal.md"),
               make_proposal(140).replace("1-min", "[N]-min"))
        code, output = self.run_main("--loom", self.LOOM, "--runtime", "1", "--start", "today",
                                     "--draft", "Friday", "--name", " ")
        self.assertEqual(code, 0, output)
        self.assertTrue(self.proposal().startswith("Hey there \U0001F44B I "), self.proposal())
        self.assertNotIn("Hey  ", self.proposal())
        self.assertIn("preview (140 chars)", output)
        self.assertIn("--name is blank", output)
        self.assert_row_count(self.log(), 140)

    def test_blank_name_on_a_rerun_changes_nothing(self):
        before = self.first_run()
        proposal = self.proposal()
        for blank in (" ", "   ", "\t"):
            with self.subTest(repr(blank)):
                code, output = self.run_main("--loom", self.LOOM, "--runtime", "1",
                                             "--start", "today", "--name", blank)
                self.assertEqual(code, 0, output)
                self.assertEqual(self.proposal(), proposal)
                self.assertIn("preview (140 chars)", output)
                self.assertIn("NOT LOGGED", output)
                self.assertEqual(self.log(), before)

    def test_padded_name_is_stripped_on_first_run_and_rerun(self):
        _write(os.path.join(self.job, "proposal.md"),
               make_proposal(140).replace("1-min", "[N]-min"))
        code, output = self.run_main("--loom", self.LOOM, "--runtime", "1", "--start", "today",
                                     "--draft", "Friday", "--name", "  Dana ")
        self.assertEqual(code, 0, output)
        self.assertTrue(self.proposal().startswith("Hey Dana \U0001F44B I "), self.proposal())
        self.assertIn("preview (139 chars)", output)
        self.assert_row_count(self.log(), 139)

        self.tearDown()
        self.setUp()
        before = self.first_run()
        code, output = self.run_main("--loom", self.LOOM, "--runtime", "1",
                                     "--start", "today", "--name", "  Dana ")
        self.assertEqual(code, 0, output)
        self.assertTrue(self.proposal().startswith("Hey Dana \U0001F44B I "), self.proposal())
        self.assertIn("updated opener_visible_chars in place on 1 existing row(s)", output)
        row = before.splitlines(True)[-1]
        self.assertEqual(self.log(), before[:-len(row)]
                         + row.replace(",standard,140,", ",standard,139,"))

    def test_fill_ignores_a_blank_name(self):
        for blank in (None, "", " ", "\t "):
            filled, _ = finalize.fill("Hey there \U0001F44B hi", SHARE + "a", 1, "today",
                                      name=blank)
            self.assertEqual(filled, "Hey there \U0001F44B hi", repr(blank))
        filled, _ = finalize.fill("Hey there \U0001F44B hi", SHARE + "a", 1, "today",
                                  name="  Dana ")
        self.assertEqual(filled, "Hey Dana \U0001F44B hi")

    def test_rerun_that_moves_the_preview_any_other_way_updates_the_count(self):
        # [DRAFT] left in the opener on the first run (no --draft), filled on
        # the re-run.
        _write(os.path.join(self.job, "proposal.md"),
               make_proposal(140).replace("1-min", "[N]-min").replace("I x", "I [DRAFT] x", 1))
        code, output = self.run_main("--loom", self.LOOM, "--runtime", "1", "--start", "today")
        self.assertEqual(code, 0, output)
        self.assertIn("logged:", output)
        before = self.log()
        self.assert_row_count(before, 148)
        code, output = self.run_main("--loom", self.LOOM, "--runtime", "1",
                                     "--start", "today", "--draft", "Fri")
        self.assertEqual(code, 0, output)
        self.assertIn("I Fri x", self.proposal())
        self.assertIn("preview (144 chars)", output)
        self.assertIn("updated opener_visible_chars in place on 1 existing row(s)", output)
        row = before.splitlines(True)[-1]
        self.assertEqual(self.log(), before[:-len(row)]
                         + row.replace(",standard,148,", ",standard,144,"))

    def five_and_three(self):
        """A preview that says "a 5-min pass" and "3-min video"."""
        return self.first_run(make_proposal(133).replace("I x", "I 5-min x", 1)
                              .replace("1-min", "[N]-min"))

    def test_replace_loom_warns_when_runtime_equals_another_token(self):
        self.five_and_three()
        # first_run filled [N] with 1; make the Loom runtime 3.
        _write(os.path.join(self.job, "proposal.md"),
               self.proposal().replace("1-min video", "3-min video"))
        proposal = self.proposal()
        code, output = self.run_main("--loom", SHARE + "zzz999", "--runtime", "5",
                                     "--start", "today", "--replace-loom")
        self.assertEqual(code, 0, output)
        self.assertIn("replaced loom: {} -> {} (runtime not applied)".format(
            self.LOOM, SHARE + "zzz999"), output)
        self.assertIn("several <n>-min tokens (5-min, 3-min), so --runtime 5 was not "
                      "applied", output)
        self.assertEqual(self.proposal(), proposal.replace(self.LOOM, SHARE + "zzz999"))
        self.assertIn("3-min video", self.proposal())
        # The same video with --runtime 5 (the retime path) warns too.
        code, output = self.run_main("--loom", SHARE + "zzz999", "--runtime", "5",
                                     "--start", "today")
        self.assertEqual(code, 0, output)
        self.assertIn("several <n>-min tokens (5-min, 3-min), so --runtime 5 was not "
                      "applied", output)
        self.assertIn("3-min video", self.proposal())

    def test_replace_loom_names_the_runtime_it_applied(self):
        self.first_run()
        code, output = self.run_main("--loom", SHARE + "zzz999", "--runtime", "4",
                                     "--start", "today", "--replace-loom")
        self.assertEqual(code, 0, output)
        self.assertIn("(4-min)", output)
        self.assertNotIn("WARNING: the preview has", output)
        self.assertIn("4-min video", self.proposal())

    def test_no_runtime_token_is_warned_on_both_paths(self):
        before = self.first_run(make_proposal(140).replace("1-min video", "a video"))
        proposal = self.proposal()
        code, output = self.run_main("--loom", self.LOOM, "--runtime", "4",
                                     "--start", "today")
        self.assertEqual(code, 0, output)
        self.assertIn("no <n>-min token, so --runtime 4 was not applied", output)
        self.assertEqual(self.proposal(), proposal)
        self.assertEqual(self.log(), before)
        code, output = self.run_main("--loom", SHARE + "zzz999", "--runtime", "4",
                                     "--start", "today", "--replace-loom")
        self.assertEqual(code, 0, output)
        self.assertIn("(runtime not applied)", output)
        self.assertIn("no <n>-min token, so --runtime 4 was not applied", output)
        self.assertEqual(self.proposal(), proposal.replace(self.LOOM, SHARE + "zzz999"))

    def test_hand_pasted_loom_with_runtime_placeholder_is_not_warned(self):
        """The Loom link pasted by hand leaves `[N]-min` in the preview; fill()
        writes --runtime into it, so no "was not applied" warning, on either
        path."""
        pasted = make_proposal(140, link=self.LOOM).replace("1-min", "[N]-min")
        for extra, loom, runtime in (((), self.LOOM, "12"),
                                     (("--replace-loom",), SHARE + "zzz999", "7")):
            with self.subTest(extra=extra):
                _write(os.path.join(self.job, "proposal.md"), pasted)
                code, output = self.run_main("--loom", loom, "--runtime", runtime,
                                             "--start", "today", "--no-log", *extra)
                self.assertEqual(code, 0, output)
                self.assertNotIn("was not applied", output)
                self.assertNotIn("runtime not applied", output)
                self.assertIn("{}-min video".format(runtime), self.proposal())
                self.assertNotIn("[N]", self.proposal())
        self.assertIn("(7-min)", output)

    def run_pasted(self, hand_tokens):
        """A hand-pasted Loom proposal whose preview has `hand_tokens` typed by
        hand plus the `[N]-min` placeholder, run with --runtime 12 on the same
        video and with --replace-loom: [(output, proposal before with the Loom
        and [START] filled, proposal after)]."""
        pasted = (make_proposal(140, link=self.LOOM).replace("1-min", "[N]-min")
                  .replace("I x", "I {} x".format(hand_tokens), 1))
        runs = []
        for extra, loom in (((), self.LOOM), (("--replace-loom",), SHARE + "zzz999")):
            with self.subTest(extra=extra):
                _write(os.path.join(self.job, "proposal.md"), pasted)
                code, output = self.run_main("--loom", loom, "--runtime", "12",
                                             "--start", "today", "--no-log", *extra)
                self.assertEqual(code, 0, output)
                runs.append((output, pasted.replace(self.LOOM, loom).replace("[START]", "today"),
                             self.proposal()))
        return runs

    def test_several_tokens_with_placeholder_fill_only_the_placeholder(self):
        """Several real tokens plus `[N]-min`: fill() writes --runtime into the
        placeholder, so no message says it was not applied, and the real
        tokens stay as they were typed."""
        (same, _, same_text), (swap, before, swap_text) = self.run_pasted("15-min 3-min")
        for output, text in ((same, same_text), (swap, swap_text)):
            self.assertNotIn("was not applied", output)
            self.assertNotIn("runtime not applied", output)
            self.assertNotIn("WARNING: the preview has", output)
            self.assertTrue(text.startswith("Hey there \U0001F44B I 15-min 3-min x"), text)
            self.assertIn("12-min video", text)
            self.assertNotIn("[N]", text)
        self.assertIn("runtime: [N]-min -> 12-min in the preview; 15-min, 3-min left as "
                      "they are", same)
        self.assertIn("replaced loom: {} -> {} ([N]-min -> 12-min; 15-min, 3-min left as "
                      "they are)".format(self.LOOM, SHARE + "zzz999"), swap)
        self.assertEqual(swap_text, before.replace("[N]-min", "12-min"))

    def test_one_token_with_placeholder_keeps_the_hand_written_token(self):
        """One real token plus `[N]-min`: --runtime fills only the placeholder;
        the `15-min` the author typed is never rewritten (the rule of
        test_several_runtime_tokens_are_never_guessed)."""
        (same, same_before, same_text), (swap, before, swap_text) = self.run_pasted("15-min")
        for output, text, was in ((same, same_text, same_before), (swap, swap_text, before)):
            self.assertEqual(text, was.replace("[N]-min", "12-min"))
            self.assertTrue(text.startswith("Hey there \U0001F44B I 15-min x"), text)
            self.assertNotIn("15-min -> 12-min", output)
            self.assertNotIn("not applied", output)
        self.assertIn("runtime: [N]-min -> 12-min in the preview; 15-min left as it is", same)
        self.assertIn("replaced loom: {} -> {} ([N]-min -> 12-min; 15-min left as it is)"
                      .format(self.LOOM, SHARE + "zzz999"), swap)

    def test_placeholder_below_the_preview_is_named_in_the_warning(self):
        """No runtime token in the preview but `[N]-min` further down: fill()
        still fills that one, so the warning says only the preview missed it."""
        pasted = make_proposal(140, link=self.LOOM).replace("1-min video", "a video").replace(
            "how it works", "how it works in [N]-min")
        for extra, loom in (((), self.LOOM), (("--replace-loom",), SHARE + "zzz999")):
            with self.subTest(extra=extra):
                _write(os.path.join(self.job, "proposal.md"), pasted)
                code, output = self.run_main("--loom", loom, "--runtime", "4",
                                             "--start", "today", "--no-log", *extra)
                self.assertEqual(code, 0, output)
                self.assertIn("no <n>-min token, so --runtime 4 was not applied to the preview "
                              "([N]-min further down still becomes 4-min)", output)
                self.assertIn("how it works in 4-min", self.proposal())
        self.assertIn("(runtime not applied to the preview)", output)

    def test_calendly_count_matches_what_the_compiler_emits(self):
        from upwork_gen.compile_n8n import to_json

        def spec(app):
            return WorkflowSpec.from_dict({
                "title": "Your Flow", "platform": "n8n",
                "nodes": [{"key": "t", "kind": "trigger.app", "app": app, "op": "invitee",
                           "label": "1 - Call Booked"},
                          {"key": "s", "kind": "app.action", "app": "slack", "op": "post",
                           "label": "2 - Tell Sales"}],
                "edges": [{"from": "t", "to": "s"}]})

        for app, expected in (("calendly", 1), ("Calendly.", 1), (" Calendly ", 1),
                              ("calendly.com", 0), ("calendly_com", 0), ("typeform", 0)):
            with self.subTest(app):
                s = spec(app)
                raw = to_json(s)
                wf = json.loads(raw)
                emitted = sum(1 for n in wf["nodes"] if "calendlyTrigger" in n["type"])
                self.assertEqual(emitted, expected)
                self.assertEqual(verify_job.calendly_spec_triggers(s), expected)
                self.assertFalse([f for f in check_n8n(wf, raw, "Your Flow", "x",
                                                       verify_job.calendly_spec_triggers(s))
                                  if "calendlyTrigger" in f])


if __name__ == "__main__":
    unittest.main()
