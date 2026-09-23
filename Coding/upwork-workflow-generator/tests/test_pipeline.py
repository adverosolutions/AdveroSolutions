"""Invariants that must hold for every archetype, on both platforms.

These are not unit tests of behaviour so much as guarantees about the artifact:
if any of them fail, something imports badly or looks wrong on camera.

    python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import json
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from upwork_gen.classify import ARCHETYPES, classify  # noqa: E402
from upwork_gen.compile_excalidraw import compile_excalidraw  # noqa: E402
from upwork_gen.compile_make import compile_make  # noqa: E402
from upwork_gen.compile_mockup import compile_mockup  # noqa: E402
from upwork_gen.compile_n8n import compile_n8n  # noqa: E402
from upwork_gen.generate import available_archetypes, load_archetype  # noqa: E402
from upwork_gen.layout import check, layout  # noqa: E402
from upwork_gen.learn import derive_keywords, load_learned, promote  # noqa: E402
from upwork_gen.mockup_theme import THEMES, initials, tile_color  # noqa: E402
from upwork_gen.spec import AI_SUB_KINDS, unique_names  # noqa: E402
import html as _html  # noqa: E402
import subprocess  # noqa: E402

ARCHETYPE_IDS = available_archetypes()


class TestVaultIntegrity(unittest.TestCase):
    def test_vault_is_populated(self):
        self.assertGreaterEqual(len(ARCHETYPE_IDS), 20, "expected the full archetype set")

    def test_classifier_ids_match_vault_files(self):
        """A classifier hit that names a file which does not exist is a 500 at
        the worst possible moment — mid-paste, with the clock running."""
        classifier_ids = {str(a["id"]) for a in ARCHETYPES}
        vault_ids = set(ARCHETYPE_IDS)
        self.assertEqual(
            classifier_ids - vault_ids, set(), "classifier names archetypes with no vault file"
        )
        self.assertEqual(
            vault_ids - classifier_ids, set(), "vault holds archetypes the classifier can never match"
        )


class TestEveryArchetype(unittest.TestCase):
    """One subtest per archetype so a failure names the culprit."""

    def test_validates(self):
        for archetype_id in ARCHETYPE_IDS:
            with self.subTest(archetype=archetype_id):
                load_archetype(archetype_id).validate()

    def test_layout_is_clean(self):
        for archetype_id in ARCHETYPE_IDS:
            with self.subTest(archetype=archetype_id):
                spec = load_archetype(archetype_id)
                spec.validate()
                self.assertEqual(check(spec, layout(spec)), [])

    def test_n8n_structure(self):
        for archetype_id in ARCHETYPE_IDS:
            with self.subTest(archetype=archetype_id):
                spec = load_archetype(archetype_id)
                spec.validate()
                workflow = compile_n8n(spec)

                names = [n["name"] for n in workflow["nodes"]]
                self.assertEqual(len(names), len(set(names)),
                                 "duplicate node names silently merge connections")

                # Every connection target must be a node that exists.
                for source, ports in workflow["connections"].items():
                    self.assertIn(source, names, "connection from unknown node")
                    for targets in ports.values():
                        for group in targets:
                            for target in group:
                                self.assertIn(target["node"], names,
                                              "connection to unknown node")

                for node in workflow["nodes"]:
                    self.assertIn("position", node)
                    self.assertEqual(len(node["position"]), 2)
                    self.assertTrue(node.get("type"))
                    self.assertIsNotNone(node.get("typeVersion"))

    def test_pins_input_and_output(self):
        """The whole pitch is 'this goes in, this comes out'. Both ends must
        actually carry data, on a node that exists."""
        for archetype_id in ARCHETYPE_IDS:
            with self.subTest(archetype=archetype_id):
                spec = load_archetype(archetype_id)
                spec.validate()
                workflow = compile_n8n(spec)
                pinned = workflow.get("pinData", {})
                self.assertEqual(len(pinned), 2, "expected data pinned on first and last node")

                names = {n["name"] for n in workflow["nodes"]}
                for name, items in pinned.items():
                    self.assertIn(name, names)
                    self.assertTrue(items and items[0].get("json"),
                                    "pinned data must not be empty")

    def test_ai_subnodes_use_typed_ports(self):
        for archetype_id in ARCHETYPE_IDS:
            with self.subTest(archetype=archetype_id):
                spec = load_archetype(archetype_id)
                spec.validate()
                workflow = compile_n8n(spec)
                # Resolve through the same de-duplication the compiler used —
                # two sub-nodes can share a label ("Claude" twice), and looking
                # up by raw label would check the first entry twice.
                names = unique_names([(n.key, n.label) for n in spec.nodes])
                for node in spec.nodes:
                    if not node.is_ai_sub:
                        continue
                    entry = workflow["connections"].get(names[node.key])
                    self.assertIsNotNone(entry, "AI sub-node {} is unwired".format(node.key))
                    port = list(entry.keys())[0]
                    self.assertTrue(port.startswith("ai_"),
                                    "AI sub-node wired on {} instead of a typed port".format(port))
                    self.assertNotIn("main", entry,
                                     "AI sub-nodes must not connect on main")

    def test_excalidraw_dsl_is_parseable(self):
        """The DSL uses [ ] { } ( ) as shape delimiters and identifies nodes by
        label text — so a label containing a delimiter is a parse error, and two
        nodes sharing a label silently merge into one."""
        for archetype_id in ARCHETYPE_IDS:
            with self.subTest(archetype=archetype_id):
                spec = load_archetype(archetype_id)
                spec.validate()
                dsl = compile_excalidraw(spec)
                body = "\n".join(
                    l for l in dsl.splitlines() if l and not l.startswith("@")
                )
                labels = [
                    x for grp in re.findall(
                        r"\[\[(.*?)\]\]|\[(.*?)\]|\{(.*?)\}|\((.*?)\)", body)
                    for x in grp if x
                ]
                self.assertTrue(labels, "no nodes emitted")
                for label in labels:
                    self.assertNotRegex(
                        label, r"[\[\]{}()]",
                        "delimiter leaked into a label — the DSL will not parse",
                    )
                names = unique_names(
                    [(n.key, n.label) for n in spec.flow_nodes])
                self.assertEqual(
                    len(set(names.values())), len(names),
                    "two nodes share a label; the DSL would merge them",
                )

    def test_diagram_matches_the_workflow_exactly(self):
        """The diagram and the workflow are narrated back to back in one
        recording. A node in one and not the other is a visible contradiction:
        you explain a step on the canvas, tab over, and it is not there."""
        for archetype_id in ARCHETYPE_IDS:
            with self.subTest(archetype=archetype_id):
                spec = load_archetype(archetype_id)
                spec.validate()
                canvas = {
                    n["name"] for n in compile_n8n(spec)["nodes"]
                    if "stickyNote" not in n["type"]
                }
                body = "\n".join(
                    l for l in compile_excalidraw(spec).splitlines()
                    if l and not l.startswith("@")
                )
                diagram = {
                    x for grp in re.findall(
                        r"\[\[(.*?)\]\]|\[(.*?)\]|\{(.*?)\}|\((.*?)\)", body)
                    for x in grp if x
                }
                self.assertEqual(
                    canvas - diagram, set(),
                    "on the n8n canvas but missing from the diagram",
                )
                self.assertEqual(
                    diagram - canvas, set(),
                    "in the diagram but not on the n8n canvas",
                )

    def test_make_structure(self):
        for archetype_id in ARCHETYPE_IDS:
            with self.subTest(archetype=archetype_id):
                spec = load_archetype(archetype_id)
                spec.validate()
                blueprint = compile_make(spec)

                ids = []
                self._walk_make(blueprint["flow"], ids, top=True)
                self.assertEqual(len(ids), len(set(ids)), "duplicate module ids")
                self.assertTrue(blueprint["flow"], "empty flow")

    def _walk_make(self, flow, ids, top=False):
        for index, module in enumerate(flow):
            ids.append(module["id"])
            self.assertTrue(module.get("module"), "module id missing")
            self.assertIn("designer", module.get("metadata", {}))
            if module.get("routes"):
                # A router is terminal at its level; anything after it would
                # produce a blueprint the Make editor cannot render.
                self.assertEqual(
                    index, len(flow) - 1,
                    "module follows a router at the same level in {}".format(module["module"]),
                )
                for route in module["routes"]:
                    # An empty route draws as a branch leading nowhere, which
                    # reads as an unfinished scenario on camera.
                    self.assertTrue(route["flow"], "router has an empty route")
                    self._walk_make(route["flow"], ids)


class TestClassifier(unittest.TestCase):
    def test_platform_detection(self):
        self.assertEqual(classify("Build me an n8n workflow for lead routing").platform, "n8n")
        self.assertEqual(classify("Need a Make.com scenario for invoices").platform, "make")
        self.assertEqual(classify("Integromat automation for our CRM").platform, "make")
        # No platform named at all still has to produce something runnable.
        self.assertEqual(classify("automate our onboarding").platform, "n8n")

    def test_vague_post_routes_to_compiler(self):
        found = classify("We need help automating some things in our business.")
        self.assertTrue(found.is_miss)
        self.assertEqual(found.engine_hint, "compiler")

    def test_confident_post_routes_to_vault(self):
        found = classify(
            "n8n RAG chatbot over our knowledge base using Pinecone vector database "
            "and OpenAI embeddings to answer customer questions"
        )
        self.assertFalse(found.is_miss)
        self.assertEqual(found.archetype, "ai_rag_chatbot")

    def test_apps_are_ordered_by_appearance(self):
        """Order decides which app takes which role when both fit one group."""
        found = classify("push to Salesforce first, then log the rest in Airtable")
        self.assertLess(found.apps.index("salesforce"), found.apps.index("airtable"))


class TestLearning(unittest.TestCase):
    """The vault grows by promoting compiler runs. These guard that growth."""

    def test_learned_archetypes_are_reachable(self):
        """A learned archetype with no keywords can never be matched — it looks
        like coverage and behaves like a gap, which is worse than not having it."""
        for archetype_id, entry in load_learned().items():
            with self.subTest(archetype=archetype_id):
                self.assertTrue(entry.get("kw"),
                                "{} has no keywords and is unreachable".format(archetype_id))

    def test_learned_archetypes_have_a_spec(self):
        vault = set(available_archetypes())
        for archetype_id in load_learned():
            with self.subTest(archetype=archetype_id):
                self.assertIn(archetype_id, vault,
                              "keywords exist with no spec file behind them")

    def test_application_boilerplate_is_not_mined(self):
        """Terms from the "to apply" tail match half of Upwork, so mining them
        would make a learned archetype fire on unrelated postings."""
        posting = (
            "Shopify Inventory Sync Specialist\n"
            "We need our warehouse stock levels synced to Shopify every hour.\n"
            "To apply, please include examples of your work for agencies and "
            "tell us why you want to become a long-term partner."
        )
        terms = {re.sub(r"\\(.)", r"\1", k) for k, _ in derive_keywords(posting)}
        for leaked in ("long-term partner", "become long-term", "agencies", "examples"):
            self.assertNotIn(leaked, terms, "mined a term from the application tail")
        self.assertTrue(any("shopify" in t or "warehouse" in t or "stock" in t for t in terms),
                        "failed to mine the terms that describe the actual work")

    def test_repromotion_does_not_degrade_keywords(self):
        """Re-promoting must not treat an archetype's own terms as taken.

        It silently did: the second promotion excluded everything the first one
        claimed and fell back to whatever weak terms were left, turning
        "insurance, receptionist" into "right now, plan timeline".
        """
        posting = ("AI receptionist for an insurance agency. Inbound agent qualifies "
                   "callers, captures policy number, books callbacks.")
        first = derive_keywords(posting, exclude="ai_receptionist_inbound")
        second = derive_keywords(posting, exclude="ai_receptionist_inbound")
        self.assertEqual(first, second, "keyword derivation is not idempotent")

    def test_nodes_are_configured(self):
        """A node whose label promises work and whose body is empty reads as a
        mock-up. Most nodes on a canvas must carry real parameters."""
        for archetype_id in ARCHETYPE_IDS:
            with self.subTest(archetype=archetype_id):
                spec = load_archetype(archetype_id)
                spec.validate()
                workflow = compile_n8n(spec)
                real = [n for n in workflow["nodes"] if "stickyNote" not in n["type"]]
                # Size is the wrong metric — a Wait node legitimately holds only
                # amount and unit. What matters is whether anything beyond
                # generic scaffolding was configured.
                scaffolding = {"options", "mode", "resource", "operation"}
                empty = [n for n in real
                         if not (set(n["parameters"]) - scaffolding)]
                self.assertLessEqual(
                    len(empty), max(2, len(real) // 4),
                    "too many empty nodes: {}".format([n["name"] for n in empty]),
                )

    def test_seed_archetypes_are_protected(self):
        """Promotion must not silently replace a hand-tuned archetype."""
        spec = load_archetype("invoice_ocr")
        report = promote(spec, job_text="invoices", archetype_id="invoice_ocr")
        self.assertFalse(report["promoted"])
        self.assertIn("force", report["reason"])


class TestBuilderMockup(unittest.TestCase):
    """The GoHighLevel / Zapier target.

    Same discipline as the Excalidraw target: the client sees the mockup and
    the workflow in one recording, so a node in one and not the other is a
    visible contradiction. These assert against the rendered page, because the
    failure mode here is a page that renders and is quietly wrong.
    """

    def _body(self, spec, theme=None):
        """Markup only — the stylesheet mentions every class name."""
        return compile_mockup(spec, theme).split("</style>", 1)[1]

    def test_every_node_reaches_the_page(self):
        for archetype_id in ARCHETYPE_IDS:
            spec = load_archetype(archetype_id)
            body = self._body(spec)
            for node in spec.nodes:
                self.assertIn(
                    _html.escape(node.label, quote=True), body,
                    "{}: {!r} ({}) never reaches the mockup".format(
                        archetype_id, node.label, node.kind),
                )

    def test_ai_sub_nodes_appear_as_chips_not_cards(self):
        """They dock on their parent in n8n; a card each would inflate the
        stack past what the workflow actually contains."""
        for archetype_id in ARCHETYPE_IDS:
            spec = load_archetype(archetype_id)
            subs = [n for n in spec.nodes if n.kind in AI_SUB_KINDS]
            if not subs:
                continue
            body = self._body(spec)
            for node in subs:
                marker = '<span class="chip"><b>'
                self.assertIn(marker, body, archetype_id)
                self.assertNotIn(
                    '<div class="ctitle">{}</div>'.format(
                        _html.escape(node.label, quote=True)),
                    body, "{}: {!r} got its own card".format(archetype_id, node.label))

    def test_every_archetype_renders_for_both_builders(self):
        for archetype_id in ARCHETYPE_IDS:
            for theme in ("ghl", "zapier"):
                page = compile_mockup(load_archetype(archetype_id), theme)
                self.assertIn("<!doctype html>", page)

    def test_page_is_completely_self_contained(self):
        """An external request that fails would repaint the page on camera."""
        page = compile_mockup(load_archetype("lead_capture_enrich_crm"))
        for pattern in (r"src\s*=", r"<link", r"@import", r"https?://"):
            self.assertIsNone(re.search(pattern, page, re.I),
                              "mockup references something external: {}".format(pattern))

    def test_spec_content_is_escaped(self):
        spec = load_archetype("lead_capture_enrich_crm")
        spec.title = "Acme <script>alert(1)</script> & Co"
        page = compile_mockup(spec)
        self.assertNotIn("<script>alert", page)
        self.assertIn("&lt;script&gt;", page)

    def test_zapier_numbers_and_ticks_while_ghl_does_neither(self):
        spec = load_archetype("lead_capture_enrich_crm")
        zapier, ghl = self._body(spec, "zapier"), self._body(spec, "ghl")
        self.assertIn('<div class="cmark">', zapier)
        self.assertIn('class="num"', zapier)
        self.assertIn('<div class="cmenu">', ghl)
        self.assertNotIn('<div class="cmark">', ghl)
        self.assertNotIn('class="num"', ghl)

    def test_branch_labels_are_client_readable(self):
        """n8n speaks true/false; nobody outside n8n does."""
        spec = load_archetype("lead_capture_enrich_crm")
        body = self._body(spec)
        self.assertNotIn('<div class="apill">true</div>', body)
        self.assertNotIn('<div class="apill">false</div>', body)

    def test_samples_land_on_the_first_and_last_card(self):
        spec = load_archetype("lead_capture_enrich_crm")
        page = compile_mockup(spec)
        self.assertEqual(page.count('<div class="data">'), 2)

    def test_tile_colours_are_stable_across_processes(self):
        """`hash()` is randomised per interpreter, so an app would change
        colour between recordings if the palette depended on it."""
        code = ("import sys; sys.path.insert(0, {!r});"
                "from upwork_gen.mockup_theme import tile_color;"
                "print(tile_color('Some Unlisted App'))").format(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        seen = set()
        for _ in range(3):
            out = subprocess.check_output([sys.executable, "-c", code],
                                          env=dict(os.environ, PYTHONHASHSEED="random"))
            seen.add(out.decode().strip())
        self.assertEqual(len(seen), 1, "tile colour is not deterministic")
        self.assertEqual(seen.pop(), tile_color("Some Unlisted App"))

    def test_initials_never_come_back_empty(self):
        for app in ("Slack", "Google Sheets", "x", "", "  ", "Go-High.Level"):
            self.assertTrue(initials(app).strip())

    def test_each_theme_defines_every_key(self):
        keys = set(THEMES["ghl"]) | set(THEMES["zapier"])
        for platform, theme in THEMES.items():
            self.assertFalse(keys - set(theme),
                             "{} is missing {}".format(platform, keys - set(theme)))


class TestArtifactHandoff(unittest.TestCase):
    def test_clip_resolves_to_the_latest_run_not_the_latest_file(self):
        """A run that skips an artifact must not silently hand over an older
        run's copy of it. That failure looks exactly like success until the
        wrong workflow's diagram is on camera."""
        import tempfile
        import time as _time

        from upwork_gen.cli import latest_run_dsl, run_slug

        with tempfile.TemporaryDirectory() as out:
            # An older, complete run.
            for suffix in (".excalidraw.dsl", ".excalidraw", ".n8n.json"):
                open(os.path.join(out, "old-job" + suffix), "w").close()
            _time.sleep(0.01)
            # A newer run that never rendered its scene.
            for suffix in (".excalidraw.dsl", ".n8n.json"):
                open(os.path.join(out, "new-job" + suffix), "w").close()

            slug = run_slug(latest_run_dsl(out))
            self.assertEqual(slug, "new-job")
            # The only .excalidraw present belongs to the older run, so asking
            # for the scene must resolve to a path that does not exist —
            # prompting a render or an error, never the stale file.
            self.assertFalse(
                os.path.exists(os.path.join(out, slug + ".excalidraw")))


if __name__ == "__main__":
    unittest.main()
