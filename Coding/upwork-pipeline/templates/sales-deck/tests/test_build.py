"""Compiler, schema, privacy and progressive batch checks (stdlib unittest)."""
import base64
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import build
from schema import ValidationError, validate, public_job


class BuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = build.read_json(ROOT / "platforms.json")
        cls.seed = build.read_json(ROOT / "examples/financial.json")
        cls.state = build.template_state()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.dir = Path(self.temp.name).resolve()
        self.job = copy.deepcopy(self.seed)

    def tearDown(self):
        self.temp.cleanup()

    def spec(self, job=None, name="spec.json"):
        path = self.dir / name
        path.write_text(json.dumps(self.job if job is None else job), encoding="utf-8")
        return path

    def invalid(self, message):
        with self.assertRaisesRegex(ValidationError, message):
            validate(self.job, self.catalog)

    def test_all_four_fixtures_compile_standalone(self):
        fixture_ids = set()
        for path in (ROOT / "examples").glob("*.json"):
            data = build.read_json(path)
            if not isinstance(data, dict) or "id" not in data:
                continue
            fixture_ids.add(data["id"])
            out = self.dir / path.stem
            report = build.compile_job(path, out, self.state)
            page = (out / "page.html").read_text()
            self.assertEqual(report["status"], "built_pending_review")
            self.assertEqual(report["visualReview"], "pending")
            self.assertIn("data:font/woff2;base64,", page)
            self.assertNotIn('<script src=', page)
            self.assertNotIn('<link ', page)
            self.assertNotIn('__INLINE_', page)
            self.assertEqual(report["files"]["page.html"], hashlib.sha256(page.encode()).hexdigest())
        self.assertEqual(fixture_ids, {"financial", "skool", "n8n-inbound-routing", "make-order-handoff"})

    def test_recursive_entities_and_numeric_leaves(self):
        self.job["entities"]["alias"] = "{{lead.name}}"
        self.job["entities"]["number"] = 42
        self.job["scenes"][1]["content"]["name"] = "{{alias}} {{number}}"
        self.assertEqual(validate(self.job, self.catalog)["scenes"][1]["content"]["name"], "Avery Morgan 42")

    def test_unresolved_token(self):
        self.job["cover"]["title"] = "{{missing.name}}"
        self.invalid("unresolved token")

    def test_entity_cycle_and_malformed_tokens(self):
        self.job["entities"]["a"] = "{{b}}"
        self.job["entities"]["b"] = "{{a}}"
        self.invalid("cyclic reference")
        self.job = copy.deepcopy(self.seed)
        self.job["cover"]["title"] = "{{broken"
        self.invalid("malformed")

    def test_duplicate_scene_and_node_ids(self):
        self.job["scenes"][1]["id"] = self.job["scenes"][0]["id"]
        self.invalid("duplicate")
        self.job = copy.deepcopy(self.seed)
        nodes = self.job["scenes"][0]["content"]["nodes"]
        nodes[1]["id"] = nodes[0]["id"]
        self.invalid("duplicate node")

    def test_invalid_edges_cycle_and_disconnected_graph(self):
        workflow = self.job["scenes"][0]["content"]
        workflow["edges"][0]["to"] = "not-found"
        self.invalid("invalid.*edge")
        self.job = copy.deepcopy(self.seed)
        workflow = self.job["scenes"][0]["content"]
        workflow["edges"].append({"from": "step-6", "to": "step-1"})
        self.invalid("acyclic")
        self.job = copy.deepcopy(self.seed)
        workflow = self.job["scenes"][0]["content"]
        workflow["edges"].pop()
        self.invalid("one trigger")

    def test_duplicate_edges_and_invalid_sample_path(self):
        workflow = self.job["scenes"][0]["content"]
        workflow["edges"].append(workflow["edges"][0])
        self.invalid("duplicate edge")
        self.job = copy.deepcopy(self.seed)
        self.job["scenes"][0]["content"]["runOrder"][1] = "absent"
        self.invalid("existing node")
        self.job = copy.deepcopy(self.seed)
        self.job["scenes"][0]["content"]["runOrder"] = ["step-1", "step-3", "step-6"]
        self.invalid("follow edges")

    def test_actions_platforms_and_trigger(self):
        self.job["scenes"][0]["content"]["nodes"][1]["type"] = "made-up"
        self.invalid("unsupported action")
        self.job = copy.deepcopy(self.seed)
        self.job["scenes"][0]["platform"] = "zapier"
        self.invalid("requires_adapter")
        self.job = copy.deepcopy(self.seed)
        self.job["scenes"][0]["content"]["nodes"][1]["type"] = "facebook_lead"
        self.invalid("one trigger")
        self.job = build.read_json(ROOT / "examples/n8n-inbound-routing.json")
        self.job["scenes"][0]["content"]["nodes"][1]["type"] = "ai_agent"
        self.invalid("unsupported action")

    def agent_job(self, platform):
        job = copy.deepcopy(self.seed)
        scene = job["scenes"][0]
        scene["platform"] = platform
        content = scene["content"]
        types = ["prompt", "read", "edit", "command", "review", "result"]
        content["nodes"] = [{"id": "task-{}".format(i), "type": kind, "label": "Sample task {}".format(i), "detail": "Project context"} for i, kind in enumerate(types)]
        content["runOrder"] = [n["id"] for n in content["nodes"]]
        content["edges"] = [{"from": a, "to": b} for a, b in zip(content["runOrder"], content["runOrder"][1:])]
        scene["statuses"] = ["Sample state"] * len(types)
        content["context"]["states"] = ["Project state"] * len(types)
        return job

    def test_agent_transcript_contract_and_custom_outputs(self):
        for platform in ("claude-code", "codex"):
            self.job = self.agent_job(platform)
            validate(self.job, self.catalog)
            for scene in self.job["scenes"][1:]:
                if scene["kind"] in ("record", "messages", "outcome"):
                    scene["platform"] = platform
            validate(self.job, self.catalog)
            page = build.page(public_job(validate(self.job, self.catalog)), self.catalog)
            self.assertNotIn('<script src=', page)
            self.assertIn('Illustrative sample', page)
        self.job = copy.deepcopy(self.seed)
        for scene in self.job["scenes"][1:]:
            scene["platform"] = "workbench"
        validate(self.job, self.catalog)

    def test_adapter_scene_compatibility_is_explicit(self):
        for platform in ("n8n", "make", "workbench", "codex", "claude-code"):
            self.job = copy.deepcopy(self.seed)
            scene = self.job["scenes"][0 if platform == "workbench" else 1]
            scene["platform"] = platform
            if platform in ("codex", "claude-code"):
                scene["kind"] = "workshop"
            self.invalid("unsupported scene/platform")
        catalog = copy.deepcopy(self.catalog)
        catalog["platforms"]["pretend"] = dict(catalog["platforms"]["ghl"])
        self.job = copy.deepcopy(self.seed)
        self.job["scenes"][1]["platform"] = "pretend"
        with self.assertRaisesRegex(ValidationError, "unsupported scene/platform"):
            validate(self.job, catalog)

    def test_agent_transcript_rejects_branches_skipped_stages_and_vendor_actions(self):
        self.job = self.agent_job("codex")
        c = self.job["scenes"][0]["content"]
        c["nodes"].append({"id": "off-path", "type": "review", "label": "Extra", "detail": "Sample"})
        c["edges"].append({"from": "task-1", "to": "off-path"})
        self.invalid("linear chain")
        self.job = self.agent_job("claude-code")
        self.job["scenes"][0]["content"]["nodes"][1]["type"] = "http_request"
        self.invalid("unsupported action")

    def test_n8n_manual_trigger_and_http_request_are_supported_without_ai_clusters(self):
        self.job = build.read_json(ROOT / "examples/n8n-inbound-routing.json")
        self.job["scenes"][0]["content"]["nodes"][0]["type"] = "manual_trigger"
        self.job["scenes"][0]["content"]["nodes"][1]["type"] = "http_request"
        validate(self.job, self.catalog)
        self.job["scenes"][0]["content"]["nodes"][1]["type"] = "chat_model"
        self.invalid("unsupported action")

    def carousel_job(self):
        job = copy.deepcopy(self.seed)
        image = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aWQAAAABJRU5ErkJggg=="
        scene = copy.deepcopy(job["scenes"][-1])
        scene.update(kind="carousel", platform="workbench", optional=False, statuses=["First photo", "Second photo"])
        scene["content"] = {"name": "Sample content", "subtitle": "Property preview", "slides": [{"title": "Photo {}".format(i), "body": "Sample property detail", "imageData": image, "alt": "Supplied property photo"} for i in range(2)], "caption": "Sample generated caption", "fields": [{"label": "Status", "value": "For review"}]}
        job["scenes"] = [job["scenes"][0], scene]
        return job

    def test_carousel_is_required_visible_proof_and_standalone_inline(self):
        self.job = self.carousel_job()
        normalized = validate(self.job, self.catalog)
        page = build.page(public_job(normalized), self.catalog)
        self.assertIn('data:image/png;base64,', page)
        self.assertNotIn('<script src=', page)
        self.job["scenes"][-1]["optional"] = True
        self.invalid("visible result/proof")

    def test_carousel_rejects_remote_svg_empty_invalid_and_mismatched_images(self):
        for value in ("https://private.example/photo.jpg", "file:///private/photo.png", "data:image/svg+xml;base64,PHN2Zz4=", "data:image/png;base64,", "data:image/png;base64,AAAA!", "data:image/jpeg;base64,aGVsbG8=", "data:image/png;base64,iVBORw0KGgoAA"):
            self.job = self.carousel_job()
            self.job["scenes"][-1]["content"]["slides"][0]["imageData"] = value
            self.invalid("image|base64")

    def test_carousel_bounds_statuses_fields_and_platform_compatibility(self):
        for count in (1, 6):
            self.job = self.carousel_job()
            c = self.job["scenes"][-1]["content"]
            c["slides"] = [c["slides"][0]] * count
            self.invalid("2..5 slides")
        self.job = self.carousel_job()
        self.job["scenes"][-1]["statuses"] = ["One"]
        self.invalid("one status")
        for platform in ("ghl", "n8n", "make", "codex", "claude-code"):
            self.job = self.carousel_job()
            self.job["scenes"][-1]["platform"] = platform
            self.invalid("unsupported scene/platform")
        self.job = self.carousel_job()
        self.job["scenes"][-1]["content"]["slides"][0]["sourceUrl"] = "https://private.example"
        self.invalid("unknown fields")

    def test_carousel_image_total_size_and_supported_signatures(self):
        for mime, raw in (("jpeg", b"\xff\xd8\xffsample"), ("png", b"\x89PNG\r\n\x1a\nsample"), ("webp", b"RIFFsample12WEBP")):
            if mime == "webp":
                raw = b"RIFF1234WEBPsample"
            self.job = self.carousel_job()
            self.job["scenes"][-1]["content"]["slides"][0]["imageData"] = "data:image/{};base64,".format(mime) + base64.b64encode(raw).decode()
            validate(self.job, self.catalog)
        self.job = self.carousel_job()
        image = "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"a" * (1024 * 1024)).decode()
        for slide in self.job["scenes"][-1]["content"]["slides"]:
            slide["imageData"] = image
        self.invalid("2 MiB total")
        self.job = self.carousel_job()
        self.job["scenes"][-1]["content"]["caption"] = "x" * 601
        self.invalid("600 characters")

    def test_n8n_if_ports(self):
        self.job = build.read_json(ROOT / "examples/n8n-inbound-routing.json")
        self.job["scenes"][0]["content"]["edges"][-1]["label"] = "true"
        self.invalid("true/false")

    def test_schema_types_bounds_and_locked_opening(self):
        self.job["cover"]["caption"] = "New opening"
        self.invalid("approved opening")
        self.job = copy.deepcopy(self.seed)
        self.job["title"] = "x" * 241
        self.invalid("240 characters")
        self.job = copy.deepcopy(self.seed)
        self.job["scenes"][0]["optional"] = "false"
        self.invalid("boolean")
        self.job = copy.deepcopy(self.seed)
        self.job["scenes"][1]["content"]["css"] = "color:red"
        self.invalid("unknown fields")

    def test_source_and_personalization_evidence_private(self):
        self.job["source"] = {"jobUrl": "https://private.example/hidden", "facts": ["PRIVATE_EVIDENCE_619"]}
        out = self.dir / "privacy"
        build.compile_job(self.spec(), out, self.state)
        for name in build.OUTPUT_FILES:
            content = (out / name).read_text()
            self.assertNotIn("PRIVATE_EVIDENCE_619", content)
            self.assertNotIn("https://private.example", content)
            self.assertNotIn("client_reviews", content)
            self.assertNotIn("reviewCount", content)
        self.assertEqual(public_job(validate(self.job, self.catalog))["personalization"], {"firstName": "Ron"})

    def test_review_name_rule(self):
        self.job["personalization"]["reviewCount"] = 1
        self.invalid("two unambiguous")
        self.job["personalization"]["source"] = "owner_guess"
        self.invalid("supplied, post")

    def test_markup_rejected_and_safe_embedding(self):
        self.job["title"] = '<img src=x onerror=alert(1)>'
        self.invalid("markup")
        encoded = build.js_json({"x": "</script>&<\u2028\u2029"})
        self.assertNotIn("<", encoded)
        self.assertNotIn("&", encoded)
        self.assertNotIn("\u2028", encoded)
        self.assertEqual(json.loads(encoded)["x"], "</script>&<\u2028\u2029")
        self.job = copy.deepcopy(self.seed)
        self.job["title"] = 'A & B < 5 "quoted"'
        self.job["cover"]["title"] = "__INLINE_FONT__"
        page = build.page(public_job(validate(self.job, self.catalog)), self.catalog)
        self.assertIn('<title>A &amp; B &lt; 5 &quot;quoted&quot;</title>', page)
        self.assertIn('"title":"__INLINE_FONT__"', page)

    def test_mutated_entities_remove_stale_seed_name(self):
        self.job["entities"]["lead"]["name"] = "Sentinel Contact"
        # Every data-bearing sample name occurrence is authored through entities.
        for scene in self.job["scenes"]:
            scene["title"] = scene["title"].replace("Avery", "{{lead.name}}")
            scene["caption"] = scene["caption"].replace("Avery", "{{lead.name}}")
        page = build.page(public_job(validate(self.job, self.catalog)), self.catalog)
        self.assertIn('"name":"Sentinel Contact"', page)
        self.assertNotIn('"name":"Avery Morgan"', page)
        runtime = (ROOT / "runtime/app.js").read_text()
        self.assertNotIn("Avery", runtime)
        self.assertNotIn("Jamie", runtime)

    def test_no_numerical_improvement_aims_or_optional_result(self):
        self.job["close"]["metrics"][0]["aim"] = "Improve 30%"
        self.invalid("numerical improvement")
        self.job = copy.deepcopy(self.seed)
        self.job["scenes"][-1]["optional"] = True
        self.invalid("visible result/proof")

    def test_atomic_generation_leaves_existing_page_on_validation_failure(self):
        out = self.dir / "atomic"
        build.compile_job(self.spec(), out, self.state)
        before = (out / "page.html").read_bytes()
        (out / "jd.txt").write_text("private post")
        self.job["scenes"][0]["platform"] = "unsupported"
        with self.assertRaises(ValidationError):
            build.compile_job(self.spec(), out, self.state)
        self.assertEqual((out / "page.html").read_bytes(), before)
        self.assertEqual((out / "jd.txt").read_text(), "private post")
        self.assertFalse(list(out.glob(".deck-stage-*")))

    def test_batch_partial_failure_and_progressive_index(self):
        good = self.spec(name="good.json")
        bad = self.dir / "bad.json"
        bad.write_text("{ invalid }")
        manifest = self.dir / "batch.json"
        manifest.write_text(json.dumps({"jobs": [good.name, bad.name]}))
        snapshots = []
        original = build.atomic_text
        def capture(path, content):
            if Path(path).name == "batch-report.json":
                snapshots.append(json.loads(content))
            return original(path, content)
        out = self.dir / "batch"
        with patch.object(build, "atomic_text", capture):
            self.assertEqual(build.batch(manifest, out, self.state), 1)
        self.assertEqual(snapshots[0]["jobs"][0]["status"], "queued")
        self.assertEqual(snapshots[-1]["jobs"][0]["status"], "built_pending_review")
        self.assertEqual(snapshots[-1]["jobs"][1]["status"], "failed")
        self.assertTrue((out / "financial/page.html").exists())
        self.assertIn('financial/page.html', (out / "index.html").read_text())

    def test_duplicate_batch_slugs_never_overwrite(self):
        first, second = self.spec(name="first.json"), self.spec(name="second.json")
        manifest = self.dir / "batch.json"
        manifest.write_text(json.dumps({"jobs": [first.name, second.name]}))
        out = self.dir / "batch"
        self.assertEqual(build.batch(manifest, out, self.state), 1)
        self.assertFalse((out / "financial/page.html").exists())
        self.assertTrue(all(e["status"] == "failed" for e in build.read_json(out / "batch-report.json")["jobs"]))

    def test_unsafe_paths_and_duplicate_json_keys(self):
        self.job["id"] = "../escape"
        self.invalid("safe lowercase slug")
        link = self.dir / "link"
        link.symlink_to(self.dir, target_is_directory=True)
        with self.assertRaisesRegex(ValidationError, "symbolic"):
            build.safe_out(link / "job")
        with self.assertRaises(ValidationError):
            build.safe_out(ROOT)
        path = self.dir / "duplicate.json"
        path.write_text('{"id":"one","id":"two"}')
        with self.assertRaisesRegex(ValidationError, "duplicate JSON"):
            build.read_json(path)

    def test_lock_drift(self):
        with patch.object(build, "ROOT", self.dir):
            for name in build.LOCK_FILES:
                path = self.dir / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("locked")
            (self.dir / "template-lock.json").write_text(json.dumps(build.template_state()))
            build.verify_lock()
            (self.dir / "schema.py").write_text("drift")
            with self.assertRaisesRegex(ValidationError, "template drift: schema.py"):
                build.verify_lock()

    def test_review_hash_promotion_rejection_and_rebuild_reset(self):
        out = self.dir / "review"
        report = build.compile_job(self.spec(), out, self.state)
        with self.assertRaisesRegex(ValidationError, "does not match"):
            build.record_review(out, "approve", "0" * 64, "Independent checks passed", self.state)
        review = build.record_review(out, "approve", report["files"]["page.html"], "Independent checks passed", self.state)
        self.assertEqual(review["status"], "reviewed_ready")
        build.record_review(out, "reject", report["files"]["page.html"], "Reviewer found a clipped message", self.state)
        self.assertEqual(build.read_json(out / "build-report.json")["visualReview"], "reject")
        build.compile_job(self.spec(), out, self.state)
        self.assertFalse((out / "review-report.json").exists())
        self.assertEqual(build.read_json(out / "build-report.json")["status"], "built_pending_review")

    def test_progressive_resume_keeps_ready_page_when_later_spec_arrives(self):
        self.spec()
        manifest = self.dir / "batch.json"
        manifest.write_text('{"jobs":["spec.json","later.json"]}')
        out = self.dir / "batch"
        self.assertEqual(build.batch(manifest, out, self.state, resume=True), 1)
        first = out / "financial"
        report = build.read_json(first / "build-report.json")
        build.record_review(first, "approve", report["files"]["page.html"], "Independent review passed", self.state)
        receipt = (first / "review-report.json").read_bytes()
        page = (first / "page.html").read_bytes()
        later = copy.deepcopy(self.seed)
        later["id"] = "later-job"
        self.spec(later, "later.json")
        self.assertEqual(build.batch(manifest, out, self.state, resume=True), 0)
        entries = build.read_json(out / "batch-report.json")["jobs"]
        self.assertEqual(entries[0]["status"], "reviewed_ready")
        self.assertTrue(entries[0]["reused"])
        self.assertEqual(entries[1]["status"], "built_pending_review")
        self.assertEqual((first / "review-report.json").read_bytes(), receipt)
        self.assertEqual((first / "page.html").read_bytes(), page)
        self.job["cover"]["title"] = "A changed opening title"
        self.spec()
        build.batch(manifest, out, self.state, resume=True)
        self.assertEqual(build.read_json(first / "build-report.json")["status"], "built_pending_review")
        self.assertFalse((first / "review-report.json").exists())

    def test_resume_rebuilds_tampered_page_and_inconsistent_receipt(self):
        self.spec()
        out = self.dir / "resume"
        report = build.compile_job(self.dir / "spec.json", out, self.state)
        build.record_review(out, "approve", report["files"]["page.html"], "Independent review passed", self.state)
        receipt = build.read_json(out / "review-report.json")
        receipt["contentHash"] = "incorrect"
        (out / "review-report.json").write_text(json.dumps(receipt))
        self.assertIsNone(build.reusable_report(self.dir / "spec.json", out, self.state, self.catalog))
        build.record_review(out, "approve", report["files"]["page.html"], "Independent review passed", self.state)
        (out / "page.html").write_text("changed page")
        self.assertIsNone(build.reusable_report(self.dir / "spec.json", out, self.state, self.catalog))

    def test_standalone_rebuild_resets_approved_parent_queue(self):
        self.spec()
        manifest = self.dir / "batch.json"
        manifest.write_text('{"jobs":["spec.json"]}')
        out = self.dir / "batch"
        build.batch(manifest, out, self.state)
        first = out / "financial"
        report = build.read_json(first / "build-report.json")
        build.record_review(first, "approve", report["files"]["page.html"], "Independent review passed", self.state)
        self.job["cover"]["title"] = "Changed after approval"
        rebuilt = build.compile_job(self.spec(), first, self.state)
        queue = build.read_json(out / "batch-report.json")
        self.assertEqual(queue["status"], "built_pending_review")
        self.assertEqual(queue["jobs"][0]["status"], "built_pending_review")
        self.assertEqual(queue["jobs"][0]["visualReview"], "pending")
        self.assertEqual(queue["jobs"][0]["contentHash"], rebuilt["contentHash"])
        self.assertNotIn("pageHash", queue["jobs"][0])
        self.assertFalse((first / "review-report.json").exists())
        index = (out / "index.html").read_text()
        self.assertIn("0 ready to record · 1 need review", index)
        self.assertIn("Needs review", index)
        self.assertNotIn(">Ready to record<", index)

    def test_huge_entity_integer_fails_one_job_without_aborting_batch(self):
        self.spec(name="good.json")
        self.job["id"] = "huge-number"
        self.job["entities"]["number"] = 10 ** 400
        self.invalid("exact browser number range")
        self.spec(name="huge.json")
        manifest = self.dir / "batch.json"
        manifest.write_text('{"jobs":["huge.json","good.json"]}')
        out = self.dir / "batch"
        self.assertEqual(build.batch(manifest, out, self.state), 1)
        queue = build.read_json(out / "batch-report.json")
        self.assertEqual(queue["jobs"][0]["status"], "failed")
        self.assertIn("exact browser number range", queue["jobs"][0]["error"])
        self.assertEqual(queue["jobs"][1]["status"], "built_pending_review")
        self.assertTrue((out / "financial/page.html").is_file())

    def test_review_promotes_parent_batch_entry(self):
        self.spec()
        manifest = self.dir / "batch.json"
        manifest.write_text('{"jobs":["spec.json"]}')
        out = self.dir / "batch"
        build.batch(manifest, out, self.state)
        report = build.read_json(out / "financial/build-report.json")
        build.record_review(out / "financial", "approve", report["files"]["page.html"], "Independent review passed", self.state)
        self.assertEqual(build.read_json(out / "batch-report.json")["status"], "reviewed_ready")
        self.assertIn("reviewed_ready", (out / "index.html").read_text())


if __name__ == "__main__":
    unittest.main()
