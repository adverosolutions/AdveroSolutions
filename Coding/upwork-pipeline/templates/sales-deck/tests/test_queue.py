"""Shared queue durability, concurrency, approval integrity and public privacy."""
import copy
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

DECK = Path(__file__).resolve().parents[1]
PIPELINE = DECK.parents[1]
sys.path.insert(0, str(DECK))
import build
import queue_engine as queue
from schema import ValidationError


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / "shared"
        self.seed = build.read_json(DECK / "examples/financial.json")

    def tearDown(self):
        self.temp.cleanup()

    def spec(self, job_id, missing=False):
        path = self.base / "source" / job_id / "deck-spec.json"
        if not missing:
            path.parent.mkdir(parents=True, exist_ok=True)
            data = copy.deepcopy(self.seed)
            data.update(id=job_id, title="Demo " + job_id)
            data["source"]["facts"].append("PRIVATE-EVIDENCE-SENTINEL")
            path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def manifest(self, rows, name="manifest"):
        path = self.base / (name + ".json")
        path.write_text(json.dumps({"jobs": rows}), encoding="utf-8")
        return path

    def row(self, job_id, spec=None):
        return {"id": job_id, "title": "Demo " + job_id,
                "spec": str(spec or self.spec(job_id)),
                "jobUrl": "https://www.upwork.com/jobs/" + job_id}

    def add(self, job_id="alpha"):
        row = self.row(job_id)
        snapshot, errors = queue.register(self.manifest([row]), self.root)
        self.assertEqual(errors, [])
        return Path(row["spec"])

    def ready(self, job_id="alpha"):
        self.add(job_id)
        snapshot, errors = queue.build_jobs([job_id], self.root)
        self.assertEqual(errors, [])
        self.assertEqual(self.job(snapshot, job_id)["status"], "built_pending_review")
        report = build.read_json(self.output(job_id) / "build-report.json")
        queue.review(job_id, "approve", report["files"]["page.html"], "Independent fixture review.", self.root)
        return report

    def output(self, job_id="alpha"):
        return self.root / "public/jobs" / job_id

    def job(self, snapshot=None, job_id="alpha"):
        if snapshot is None:
            snapshot = queue.public_snapshot(self.root)
        return next(job for job in snapshot["jobs"] if job["id"] == job_id)

    def run_cli(self, *args, root_after=False):
        command = [str(PIPELINE / "recording-queue")]
        command.extend(args if root_after else ["--root", str(self.root)] + list(args))
        if root_after:
            command.extend(["--root", str(self.root)])
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        return subprocess.run(command, cwd="/", env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)

    def test_default_root_and_wrapper_have_no_cwd_dependency(self):
        self.assertEqual(queue.DEFAULT_ROOT, Path.home() / "Desktop/AdveroSolutions/Coding/upwork-pipeline/.local/recording-queue")
        manifest = self.manifest([self.row("alpha")])
        result = self.run_cli("register", str(manifest), root_after=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.run_cli("build")
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.run_cli("status", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.job(json.loads(result.stdout))["status"], "built_pending_review")

    def test_start_cli_prints_returned_server_details_and_uses_default_port(self):
        import queue_server
        for details in ({"url": "http://127.0.0.1:8769/", "reused": False, "pid": 1234},
                        {"url": "http://127.0.0.1:8769/", "reused": True}):
            stdout = io.StringIO()
            with patch.object(queue_server, "start", return_value=details) as start:
                with redirect_stdout(stdout):
                    result = queue.main(["--root", str(self.root), "start"])
            self.assertEqual(result, 0)
            self.assertEqual(json.loads(stdout.getvalue()), details)
            start.assert_called_once_with(self.root, queue_server.DEFAULT_PORT)

    def test_relative_and_absolute_spec_registration_is_idempotent(self):
        spec = self.spec("alpha")
        relative = self.row("alpha", spec.relative_to(self.base))
        path = self.manifest([relative, relative])
        snapshot, errors = queue.register(path, self.root)
        self.assertEqual(errors, [])
        self.assertEqual(len(snapshot["jobs"]), 1)
        row = self.row("alpha", spec)
        row["title"] = "Changed manifest title"
        snapshot, errors = queue.register(self.manifest([row]), self.root)
        self.assertEqual(errors, [])
        self.assertEqual(snapshot["jobs"][0]["title"], "Demo alpha")
        self.assertEqual(len(snapshot["jobs"]), 1)

    def test_conflicting_duplicate_rows_all_refused_before_generation(self):
        first = self.row("alpha")
        second = dict(first, spec=str(self.spec("beta")))
        snapshot, errors = queue.register(self.manifest([first, second, self.row("gamma")]), self.root)
        self.assertEqual(len(errors), 1)
        self.assertEqual([j["id"] for j in snapshot["jobs"]], ["gamma"])
        self.assertFalse(self.output("alpha").exists())

    def test_conflicting_existing_registration_preserves_exact_approval(self):
        self.ready()
        before = (self.output() / "review-report.json").read_bytes()
        row = self.row("alpha", self.spec("beta"))
        snapshot, errors = queue.register(self.manifest([row, self.row("gamma")]), self.root)
        self.assertEqual(len(errors), 1)
        self.assertEqual(self.job(snapshot)["status"], "reviewed_ready")
        self.assertEqual((self.output() / "review-report.json").read_bytes(), before)
        original = self.row("alpha", self.base / "source/alpha/deck-spec.json")
        original["jobUrl"] = "https://www.upwork.com/jobs/different"
        snapshot, errors = queue.register(self.manifest([original]), self.root)
        self.assertEqual(len(errors), 1)
        self.assertEqual(self.job(snapshot)["jobUrl"], "https://www.upwork.com/jobs/alpha")

    def test_missing_specs_and_partial_failures_preserve_other_jobs(self):
        good = self.row("good")
        missing = self.row("later", self.spec("later", missing=True))
        invalid_path = self.spec("broken")
        invalid_path.write_text('{"id": "broken"}', encoding="utf-8")
        rows = [good, missing, self.row("broken", invalid_path), {"id": "../unsafe"}]
        snapshot, errors = queue.register(self.manifest(rows), self.root)
        self.assertEqual(len(errors), 1)
        self.assertEqual(self.job(snapshot, "later")["status"], "queued")
        snapshot, errors = queue.build_jobs(root=self.root)
        self.assertEqual(len(errors), 1)
        self.assertTrue(errors[0].startswith("broken: "))
        self.assertEqual(self.job(snapshot, "good")["status"], "built_pending_review")
        self.assertEqual(self.job(snapshot, "later")["status"], "queued")
        self.assertNotIn("error", self.job(snapshot, "later"))
        self.assertEqual(self.job(snapshot, "broken")["status"], "failed")
        self.assertEqual(self.job(job_id="later")["status"], "queued")
        self.assertEqual(self.job(job_id="broken")["status"], "failed")
        snapshot, errors = queue.build_jobs(["later"], self.root)
        self.assertEqual(errors, [])
        self.assertEqual(self.job(snapshot, "later")["status"], "queued")
        entry = next(j for j in build.read_json(self.root / queue.REGISTRY)["jobs"] if j["id"] == "later")
        for key in ("generation", "error", "buildError", "failedSpecHash", "privateError"):
            self.assertNotIn(key, entry)
        self.spec("later")
        self.assertEqual(self.job(job_id="later")["status"], "queued")
        snapshot, errors = queue.build_jobs(["later", "unknown"], self.root)
        self.assertEqual(len(errors), 1)
        self.assertEqual(self.job(snapshot, "later")["status"], "built_pending_review")
        self.assertEqual([j["id"] for j in snapshot["jobs"]], ["good", "later", "broken"])

    def test_missing_spec_cli_build_succeeds_and_status_remains_queued(self):
        manifest = self.manifest([self.row("later", self.spec("later", missing=True))])
        result = self.run_cli("register", str(manifest))
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.run_cli("build")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        result = self.run_cli("status", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        job = self.job(json.loads(result.stdout), "later")
        self.assertEqual(job["status"], "queued")
        self.assertNotIn("error", job)

    def test_missing_unbuilt_spec_clears_failure_from_malformed_spec(self):
        spec = self.add()
        spec.write_text("not-json", encoding="utf-8")
        snapshot, errors = queue.build_jobs(root=self.root)
        self.assertEqual(len(errors), 1)
        self.assertEqual(self.job(snapshot)["status"], "failed")
        self.assertEqual(self.job()["status"], "failed")
        spec.unlink()
        self.assertEqual(self.job()["status"], "queued")
        snapshot, errors = queue.build_jobs(root=self.root)
        self.assertEqual(errors, [])
        self.assertEqual(self.job(snapshot)["status"], "queued")
        entry = build.read_json(self.root / queue.REGISTRY)["jobs"][0]
        for key in ("error", "buildError", "failedSpecHash", "privateError"):
            self.assertNotIn(key, entry)

    def test_missing_spec_from_prior_generation_still_requires_rebuild(self):
        self.ready()
        spec = self.base / "source/alpha/deck-spec.json"
        original = spec.read_bytes()
        spec.unlink()
        self.assertEqual(self.job()["status"], "needs_build")
        snapshot, errors = queue.build_jobs(root=self.root)
        self.assertEqual(len(errors), 1)
        self.assertEqual(self.job(snapshot)["status"], "needs_build")
        self.assertIsNone(self.job(snapshot)["pageUrl"])
        spec.write_bytes(original)
        self.assertEqual(self.job()["status"], "needs_build")
        snapshot, errors = queue.build_jobs(root=self.root)
        self.assertEqual(errors, [])
        self.assertEqual(self.job(snapshot)["status"], "built_pending_review")

    def test_spec_id_cannot_write_to_another_registered_job(self):
        self.ready("alpha")
        self.add("beta")
        before = (self.output("alpha") / "page.html").read_bytes()
        path = self.base / "source/beta/deck-spec.json"
        data = build.read_json(path)
        data["id"] = "alpha"
        path.write_text(json.dumps(data), encoding="utf-8")
        snapshot, errors = queue.build_jobs(["beta"], self.root)
        self.assertEqual(len(errors), 1)
        self.assertEqual(self.job(snapshot, "beta")["status"], "failed")
        self.assertEqual(self.job(snapshot, "alpha")["status"], "reviewed_ready")
        self.assertEqual((self.output("alpha") / "page.html").read_bytes(), before)

    def test_unchanged_approved_page_survives_unrelated_batch_and_build(self):
        self.ready()
        before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.output().iterdir()}
        later = self.row("later")
        queue.register(self.manifest([later], "later-manifest"), self.root)
        snapshot, errors = queue.build_jobs(root=self.root)
        self.assertEqual(errors, [])
        self.assertEqual(self.job(snapshot)["status"], "reviewed_ready")
        after = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.output().iterdir()}
        self.assertEqual(after, before)

    def test_any_spec_byte_change_invalidates_and_rebuilds_to_pending(self):
        report = self.ready()
        spec = self.base / "source/alpha/deck-spec.json"
        original = spec.read_bytes()
        spec.write_bytes(original + b"\n")
        self.assertEqual(self.job()["status"], "needs_build")
        with self.assertRaises(ValidationError):
            queue.review("alpha", "approve", report["files"]["page.html"], "Stale review", self.root)
        # Restoring the bytes cannot resurrect a previously invalidated approval.
        spec.write_bytes(original)
        self.assertEqual(self.job()["status"], "needs_build")
        snapshot, errors = queue.build_jobs(["alpha"], self.root)
        self.assertEqual(errors, [])
        self.assertEqual(self.job(snapshot)["status"], "built_pending_review")
        self.assertFalse((self.output() / "review-report.json").exists())

    def test_each_artifact_and_receipt_tamper_invalidates_approval(self):
        for filename in ("page.html", "recording-script.txt", "build-report.json", "review-report.json"):
            with self.subTest(filename=filename):
                job_id = "tamper-" + filename.split(".")[0].replace("-", "")
                self.ready(job_id)
                path = self.output(job_id) / filename
                path.write_bytes(path.read_bytes() + b"\n")
                job = self.job(job_id=job_id)
                self.assertEqual(job["status"], "needs_build")
                self.assertIsNone(job["pageUrl"])

    def test_deleted_review_or_script_and_template_drift_are_not_ready(self):
        self.ready("deleted")
        (self.output("deleted") / "review-report.json").unlink()
        self.assertEqual(self.job(job_id="deleted")["status"], "needs_build")
        self.ready("template")
        with patch.object(build, "verify_lock", side_effect=ValidationError("private template path")):
            snapshot = queue.public_snapshot(self.root)
        self.assertEqual(self.job(snapshot, "template")["status"], "needs_build")
        self.assertNotIn("private template path", json.dumps(snapshot))

    def test_wrong_page_hash_cannot_approve_and_rejection_is_distinct(self):
        self.add()
        queue.build_jobs(root=self.root)
        with self.assertRaises(ValidationError):
            queue.review("alpha", "approve", "0" * 64, "Incorrect page", self.root)
        self.assertEqual(self.job()["status"], "built_pending_review")
        report = build.read_json(self.output() / "build-report.json")
        snapshot = queue.review("alpha", "reject", report["files"]["page.html"], "Needs repairs", self.root)
        self.assertEqual(self.job(snapshot)["status"], "review_rejected")
        with self.assertRaises(ValidationError):
            queue.recorded("alpha", root=self.root)
        snapshot, errors = queue.build_jobs(root=self.root)
        self.assertEqual(errors, [])
        self.assertEqual(self.job(snapshot)["status"], "review_rejected")

    def test_recorded_receipt_binds_exact_generation_and_reopen_preserves_approval(self):
        self.add()
        with self.assertRaises(ValidationError):
            queue.recorded("alpha", root=self.root)
        self.ready("beta")
        self.assertEqual(self.job(queue.recorded("beta", "https://www.loom.com/share/test", self.root), "beta")["status"], "recorded")
        self.assertEqual(self.job(job_id="beta")["status"], "recorded")
        snapshot, errors = queue.build_jobs(["beta"], self.root)
        self.assertEqual(errors, [])
        self.assertEqual(self.job(snapshot, "beta")["status"], "recorded")
        self.assertEqual(self.job(queue.reopen("beta", self.root), "beta")["status"], "reviewed_ready")
        queue.recorded("beta", root=self.root)
        spec = self.base / "source/beta/deck-spec.json"
        spec.write_bytes(spec.read_bytes() + b"\n")
        self.assertEqual(self.job(job_id="beta")["status"], "needs_build")
        registry = build.read_json(self.root / queue.REGISTRY)
        self.assertNotIn("recording", next(j for j in registry["jobs"] if j["id"] == "beta"))
        snapshot, errors = queue.build_jobs(["beta"], self.root)
        self.assertEqual(errors, [])
        self.assertEqual(self.job(snapshot, "beta")["status"], "built_pending_review")

    def test_public_projection_contains_no_private_paths_evidence_or_receipts(self):
        self.ready()
        queue.recorded("alpha", "https://www.loom.com/share/private-recording", self.root)
        missing = self.row("missing", self.base / "PRIVATE-SPEC-PATH.json")
        queue.register(self.manifest([missing]), self.root)
        queue.build_jobs(["missing"], self.root)
        snapshot = queue.public_snapshot(self.root)
        public = json.dumps(snapshot)
        self.assertEqual(set(snapshot), {"schemaVersion", "updatedAt", "counts", "jobs"})
        for value in (str(self.base), "PRIVATE-EVIDENCE-SENTINEL", "PRIVATE-SPEC-PATH", "private-recording", "specHash", "contentHash", "notes", "registry.json"):
            self.assertNotIn(value, public)
        self.assertEqual(self.job(snapshot)["pageUrl"], "/jobs/alpha/page.html")
        self.assertEqual(self.job(snapshot)["recordingScriptUrl"], "/jobs/alpha/recording-script.txt")
        registry = build.read_json(self.root / queue.REGISTRY)
        self.assertIn("spec", registry["jobs"][0])
        self.assertEqual((self.root / queue.REGISTRY).stat().st_mode & 0o777, 0o600)
        self.assertNotIn("PRIVATE-EVIDENCE-SENTINEL", (self.output() / "page.html").read_text())

    def test_bad_manifest_does_not_replace_registry_and_unsafe_urls_fail(self):
        self.ready()
        corrupt = self.base / "bad.json"
        corrupt.write_text("not-json", encoding="utf-8")
        with self.assertRaises(ValidationError):
            queue.register(corrupt, self.root)
        for url in ("javascript:alert(1)", "file:///private/source", "https://user:pass@example.com", "https://example.com\n"):
            row = self.row("unsafe")
            row["jobUrl"] = url
            snapshot, errors = queue.register(self.manifest([row]), self.root)
            self.assertEqual(len(errors), 1)
            self.assertEqual([j["id"] for j in snapshot["jobs"]], ["alpha"])
        self.assertEqual(self.job()["status"], "reviewed_ready")

    def test_symlinked_generated_directory_never_writes_outside_queue(self):
        self.add()
        public_jobs = self.root / "public/jobs"
        public_jobs.mkdir(parents=True)
        external = self.base / "external"
        external.mkdir()
        (public_jobs / "alpha").symlink_to(external, target_is_directory=True)
        snapshot, errors = queue.build_jobs(root=self.root)
        self.assertEqual(len(errors), 1)
        self.assertEqual(list(external.iterdir()), [])
        self.assertEqual(self.job(snapshot)["status"], "failed")

    def test_concurrent_independent_batches_build_review_and_status_never_lose_jobs(self):
        script = """
import json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import queue_engine as q
root, manifest, job = sys.argv[2:]
snapshot, errors = q.register(manifest, root)
assert not errors, errors
snapshot, errors = q.build_jobs([job], root)
assert not errors, errors
report = json.loads((Path(root) / 'public/jobs' / job / 'build-report.json').read_text())
q.review(job, 'approve', report['files']['page.html'], 'Independent fixture review', root)
for _ in range(3):
    q.public_snapshot(root)
"""
        processes = []
        for i in range(6):
            job_id = "job-" + str(i)
            manifest = self.manifest([self.row(job_id)], job_id)
            processes.append(subprocess.Popen(["/usr/bin/python3", "-c", script, str(DECK), str(self.root), str(manifest), job_id],
                                              cwd="/", env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
                                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
        for process in processes:
            out, err = process.communicate(timeout=45)
            self.assertEqual(process.returncode, 0, out + err)
        snapshot = queue.public_snapshot(self.root)
        self.assertEqual(len(snapshot["jobs"]), 6)
        self.assertEqual({j["id"] for j in snapshot["jobs"]}, {"job-" + str(i) for i in range(6)})
        self.assertEqual(snapshot["counts"]["reviewed_ready"], 6)
        order = [j["id"] for j in snapshot["jobs"]]
        self.assertEqual([j["id"] for j in queue.public_snapshot(self.root)["jobs"]], order)

    def test_registry_corruption_is_refused_without_overwriting(self):
        self.add()
        path = self.root / queue.REGISTRY
        path.write_text('{"schemaVersion": 999, "jobs": []}', encoding="utf-8")
        before = path.read_bytes()
        with self.assertRaises(ValidationError):
            queue.public_snapshot(self.root)
        self.assertEqual(path.read_bytes(), before)

    def test_independent_rebuild_resets_ready_and_recorded_state(self):
        self.ready()
        queue.recorded("alpha", root=self.root)
        spec = self.base / "source/alpha/deck-spec.json"
        build.compile_job(spec, self.output(), build.verify_lock())
        self.assertEqual(self.job()["status"], "needs_build")
        with self.assertRaises(ValidationError):
            queue.recorded("alpha", root=self.root)
        snapshot, errors = queue.build_jobs(root=self.root)
        self.assertEqual(errors, [])
        self.assertEqual(self.job(snapshot)["status"], "built_pending_review")

    def test_spec_edit_during_review_cannot_leave_approved_receipt_current(self):
        self.add()
        queue.build_jobs(root=self.root)
        spec = self.base / "source/alpha/deck-spec.json"
        report = build.read_json(self.output() / "build-report.json")
        original = build.record_review
        def mutate_after_receipt(*args, **kwargs):
            result = original(*args, **kwargs)
            spec.write_bytes(spec.read_bytes() + b"\n")
            return result
        with patch.object(build, "record_review", side_effect=mutate_after_receipt):
            with self.assertRaises(ValidationError):
                queue.review("alpha", "approve", report["files"]["page.html"], "Independent review", self.root)
        self.assertEqual(self.job()["status"], "needs_build")

    def test_completed_jobs_are_durable_when_later_build_is_interrupted(self):
        self.add("alpha")
        self.add("beta")
        original = build.compile_job
        def interrupt_second(spec, out, state, catalog):
            if out.name == "beta":
                raise KeyboardInterrupt()
            return original(spec, out, state, catalog)
        with patch.object(build, "compile_job", side_effect=interrupt_second):
            with self.assertRaises(KeyboardInterrupt):
                queue.build_jobs(root=self.root)
        snapshot = queue.public_snapshot(self.root)
        self.assertEqual(self.job(snapshot, "alpha")["status"], "built_pending_review")
        self.assertEqual(self.job(snapshot, "beta")["status"], "queued")

    def test_concurrent_conflicting_ids_have_one_winner_without_overwrite(self):
        processes = []
        for i in range(4):
            source = self.base / ("candidate-" + str(i) + ".json")
            data = copy.deepcopy(self.seed)
            data["id"] = "collision"
            source.write_text(json.dumps(data), encoding="utf-8")
            manifest = self.manifest([self.row("collision", source)], "collision-" + str(i))
            processes.append(subprocess.Popen(["/usr/bin/python3", str(DECK / "queue_engine.py"), "--root", str(self.root), "register", str(manifest)],
                                              cwd="/", env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
                                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
        codes = []
        for process in processes:
            out, err = process.communicate(timeout=30)
            self.assertIn(process.returncode, (0, 1), out + err)
            codes.append(process.returncode)
        self.assertEqual(codes.count(0), 1)
        self.assertEqual(codes.count(1), 3)
        registry = build.read_json(self.root / queue.REGISTRY)
        self.assertEqual(len(registry["jobs"]), 1)
        chosen_spec = registry["jobs"][0]["spec"]
        snapshot, errors = queue.build_jobs(root=self.root)
        self.assertEqual(errors, [])
        self.assertEqual(self.job(snapshot, "collision")["status"], "built_pending_review")
        self.assertEqual(build.read_json(self.root / queue.REGISTRY)["jobs"][0]["spec"], chosen_spec)


if __name__ == "__main__":
    unittest.main()
