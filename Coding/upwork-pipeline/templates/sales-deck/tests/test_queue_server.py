"""Loopback server boundaries and lifecycle checks; no model or live calls."""
import copy
import hashlib
import http.client
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import queue_server


class QueueServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.artifacts = self.root / "public/jobs/job-one"
        self.artifacts.mkdir(parents=True)
        (self.artifacts / "page.html").write_text("<h1>Demo one</h1>", encoding="utf-8")
        (self.artifacts / "recording-script.txt").write_text("Recording notes one", encoding="utf-8")
        (self.root / "registry.json").write_text('{"private":"PRIVATE REGISTRY"}', encoding="utf-8")
        (self.artifacts / "build-report.json").write_text("PRIVATE REPORT", encoding="utf-8")
        self.snapshot = {"schemaVersion": 1, "updatedAt": "2026-10-14T18:00:00Z",
                         "counts": {"reviewed_ready": 1}, "jobs": [
                             {"id": "job-one", "title": "A ready demo", "status": "reviewed_ready",
                              "pageUrl": "/jobs/job-one/page.html",
                              "recordingScriptUrl": "/jobs/job-one/recording-script.txt"}]}
        self.engine = SimpleNamespace(queue_root=lambda root: Path(root),
                                      public_snapshot=Mock(side_effect=lambda root: copy.deepcopy(self.snapshot)))
        self.engine_patch = patch.object(queue_server, "_engine", return_value=self.engine)
        self.engine_patch.start()
        self.server = queue_server._make_server(self.root, 0)
        self.server.RequestHandlerClass.log_message = Mock()
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.engine_patch.stop()
        self.temp.cleanup()

    def request(self, path, method="GET", headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=2)
        try:
            connection.request(method, path, headers=headers or {})
            response = connection.getresponse()
            return response.status, response.read(), dict(response.getheaders())
        finally:
            connection.close()

    def test_health_identity_canonical_digest_and_loopback_bind(self):
        status, body, headers = self.request("/health")
        self.assertEqual(status, 200)
        health = json.loads(body)
        self.assertEqual(health, {"app": queue_server.APP_ID, "schemaVersion": 1,
                                  "rootDigest": hashlib.sha256(str(self.root).encode()).hexdigest()})
        self.assertNotIn(str(self.root).encode(), body)
        self.assertEqual(self.server.server_address[0], "127.0.0.1")
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(self.request("/health", headers={"Host": "elsewhere.example"})[0], 403)

    def test_snapshot_is_fresh_and_explicit_links_are_active(self):
        first = json.loads(self.request("/queue.json")[1])
        self.assertEqual(self.request(first["jobs"][0]["pageUrl"])[1], b"<h1>Demo one</h1>")
        self.assertEqual(self.request(first["jobs"][0]["recordingScriptUrl"])[1], b"Recording notes one")
        self.snapshot["jobs"][0]["status"] = "recorded"
        self.snapshot["counts"] = {"recorded": 1}
        self.snapshot["updatedAt"] = "2026-10-14T18:01:00Z"
        second = json.loads(self.request("/queue.json")[1])
        self.assertEqual(second["jobs"][0]["status"], "recorded")
        self.assertEqual(second["counts"], {"recorded": 1})
        self.assertNotEqual(first["updatedAt"], second["updatedAt"])
        self.assertGreaterEqual(self.engine.public_snapshot.call_count, 4)

    def test_only_the_snapshot_authorizes_each_artifact(self):
        self.snapshot["jobs"][0]["pageUrl"] = None
        self.assertEqual(self.request("/jobs/job-one/page.html")[0], 404)
        self.assertEqual(self.request("/jobs/job-one/recording-script.txt")[0], 200)
        self.snapshot["jobs"][0]["recordingScriptUrl"] = "/jobs/another-job/recording-script.txt"
        self.assertEqual(self.request("/jobs/job-one/recording-script.txt")[0], 404)
        self.snapshot["jobs"] = []
        self.assertEqual(self.request("/jobs/job-one/page.html")[0], 404)

    def test_private_data_and_noncanonical_paths_are_not_served(self):
        blocked = ["/registry.json", "/public/registry.json", "/jobs/", "/public/jobs/",
                   "/jobs/job-one/", "/jobs/job-one/build-report.json", "/queue_engine.py",
                   "/server.log", "/server.pid", "/jobs/job-one/evidence.txt",
                   "/jobs/../registry.json", "/jobs/job-one/../../registry.json",
                   "/jobs/%2e%2e/registry.json", "/jobs/job-one/%70age.html",
                   "/jobs/job-one%2f..%2f../registry.json", "/jobs/%252e%252e/registry.json",
                   "/jobs/job-one/page.html%00", "/jobs/job-one\\page.html",
                   "//jobs/job-one/page.html", "/jobs/job-one/./page.html"]
        for path in blocked:
            with self.subTest(path=path):
                status, body, _ = self.request(path)
                self.assertEqual(status, 404)
                self.assertNotIn(b"PRIVATE", body)

    def test_symbolic_links_cannot_serve_private_or_external_files(self):
        page = self.artifacts / "page.html"
        page.unlink()
        page.symlink_to(self.root / "registry.json")
        self.assertEqual(self.request("/jobs/job-one/page.html")[0], 404)
        page.unlink()
        page.write_text("ordinary demo", encoding="utf-8")
        real_job = self.artifacts.with_name("renamed-job")
        self.artifacts.rename(real_job)
        self.artifacts.symlink_to(real_job, target_is_directory=True)
        self.assertEqual(self.request("/jobs/job-one/page.html")[0], 404)

    def test_read_only_head_and_error_states(self):
        status, body, _ = self.request("/", method="HEAD")
        self.assertEqual(status, 200)
        self.assertEqual(body, b"")
        for method in ("POST", "PUT", "PATCH", "DELETE", "OPTIONS"):
            with self.subTest(method=method):
                self.assertEqual(self.request("/queue.json", method=method)[0], 405)
        self.engine.public_snapshot.assert_not_called()
        self.engine.public_snapshot.side_effect = RuntimeError("PRIVATE evidence at " + str(self.root))
        status, body, _ = self.request("/queue.json")
        self.assertEqual(status, 503)
        self.assertNotIn(b"PRIVATE", body)
        self.assertNotIn(str(self.root).encode(), body)

    def test_index_and_only_approved_font_asset(self):
        status, body, headers = self.request("/")
        self.assertEqual(status, 200)
        self.assertIn(b"Recording queue", body)
        self.assertIn(b"Paste job posts into Codex chat", body)
        self.assertIn("text/html", headers["Content-Type"])
        self.assertEqual(self.request("/assets/inter-variable.woff2")[0], 200)
        self.assertEqual(self.request("/assets/../queue.html")[0], 404)

    def test_start_reuses_only_matching_healthy_queue(self):
        with patch.object(queue_server.subprocess, "Popen") as spawn:
            result = queue_server.start(self.root / ".", self.port)
            self.assertEqual(result, {"url": "http://127.0.0.1:%s/" % self.port, "reused": True})
            spawn.assert_not_called()
            with self.assertRaisesRegex(RuntimeError, "already in use"):
                queue_server.start(self.root / "other-queue", self.port)
            spawn.assert_not_called()

    def test_start_refuses_a_different_service_without_spawning(self):
        with patch.object(queue_server, "_probe", return_value=("occupied", {"app": "other"})), patch.object(queue_server.subprocess, "Popen") as spawn:
            with self.assertRaisesRegex(RuntimeError, "another service"):
                queue_server.start(self.root, self.port)
            spawn.assert_not_called()

    def test_detached_start_retains_log_and_pid_diagnostics(self):
        log = self.root / "server.log"
        log.write_text("previous diagnostics\n", encoding="utf-8")
        process = Mock(pid=12345)
        process.poll.return_value = None
        with patch.object(queue_server, "_probe", side_effect=[("free", None), ("occupied", queue_server._health(self.root))]), patch.object(queue_server.subprocess, "Popen", return_value=process) as spawn:
            result = queue_server.start(self.root, 8769)
        self.assertEqual(result["pid"], 12345)
        self.assertFalse(result["reused"])
        args, kwargs = spawn.call_args
        self.assertEqual(args[0][-4:], ["--root", str(self.root), "--port", "8769"])
        self.assertTrue(kwargs["start_new_session"])
        self.assertEqual(kwargs["stdin"], queue_server.subprocess.DEVNULL)
        self.assertEqual(log.read_text(), "previous diagnostics\n")
        self.assertEqual((self.root / "server.pid").read_text(), "12345\n")

    def test_failed_start_preserves_diagnostics(self):
        process = Mock(pid=12346)
        process.poll.return_value = 1
        with patch.object(queue_server, "_probe", return_value=("free", None)), patch.object(queue_server.subprocess, "Popen", return_value=process):
            with self.assertRaisesRegex(RuntimeError, "did not start"):
                queue_server.start(self.root, 8769)
        self.assertTrue((self.root / "server.log").exists())
        self.assertEqual((self.root / "server.pid").read_text(), "12346\n")


class RealEngineIntegrationTests(unittest.TestCase):
    def test_registered_job_build_refresh_and_revoked_artifact(self):
        import queue_engine
        template = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary).resolve()
            root = folder / "queue"
            spec = json.loads((template / "examples/financial.json").read_text())
            spec["id"] = "integration-demo"
            spec_path = folder / "spec.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            manifest = folder / "manifest.json"
            manifest.write_text(json.dumps({"jobs": [{"id": spec["id"], "title": "Integration demo",
                                                       "spec": str(spec_path),
                                                       "jobUrl": "https://www.upwork.com/jobs/example"}]}), encoding="utf-8")
            snapshot, errors = queue_engine.register(manifest, root)
            self.assertEqual(errors, [])
            self.assertEqual(snapshot["jobs"][0]["status"], "queued")
            server = queue_server._make_server(root, 0)
            server.RequestHandlerClass.log_message = Mock()
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()

            def fetch(path):
                connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
                try:
                    connection.request("GET", path)
                    response = connection.getresponse()
                    return response.status, response.read()
                finally:
                    connection.close()

            try:
                self.assertIsNone(json.loads(fetch("/queue.json")[1])["jobs"][0]["pageUrl"])
                _, errors = queue_engine.build_jobs(root=root)
                self.assertEqual(errors, [])
                built = json.loads(fetch("/queue.json")[1])
                job = built["jobs"][0]
                self.assertEqual(job["status"], "built_pending_review")
                self.assertEqual(fetch(job["pageUrl"])[0], 200)
                self.assertEqual(fetch(job["recordingScriptUrl"])[0], 200)
                self.assertEqual(fetch("/registry.json")[0], 404)
                self.assertNotIn(str(spec_path), json.dumps(built))
                page = root / "public/jobs/integration-demo/page.html"
                page.write_text("corrupted generation", encoding="utf-8")
                changed = json.loads(fetch("/queue.json")[1])
                self.assertEqual(changed["jobs"][0]["status"], "needs_build")
                self.assertIsNone(changed["jobs"][0]["pageUrl"])
                self.assertEqual(fetch(job["pageUrl"])[0], 404)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)


class QueueUIBehaviorTests(unittest.TestCase):
    def test_polling_preserves_focus_and_links_with_filter_and_error_states(self):
        template = Path(__file__).resolve().parents[1]
        node = shutil.which("node")
        if not node or not (template / "node_modules/jsdom").is_dir():
            self.skipTest("Optional existing jsdom runtime is unavailable")
        script = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const {JSDOM} = require('jsdom');
const html = fs.readFileSync('queue.html','utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const dom = new JSDOM(html,{url:'http://127.0.0.1:8769/',runScripts:'outside-only'});
const w = dom.window; const $ = id => w.document.getElementById(id);
let poll; let disconnected = false;
let snapshot = {schemaVersion:1,updatedAt:'2026-10-14T18:00:00Z',counts:{reviewed_ready:1,built_pending_review:1,needs_build:1},jobs:[
  {id:'ready-one',title:'Ready <img onerror="alert(1)">',status:'reviewed_ready',pageUrl:'/jobs/ready-one/page.html',recordingScriptUrl:'/jobs/ready-one/recording-script.txt',jobUrl:'https://www.upwork.com/jobs/example'},
  {id:'pending-two',title:'Pending demo',status:'built_pending_review',pageUrl:'/jobs/pending-two/page.html',recordingScriptUrl:'/jobs/pending-two/recording-script.txt',jobUrl:'javascript:alert(1)'},
  {id:'missing-three',title:'Needs content',status:'needs_build',pageUrl:null,recordingScriptUrl:null}
]};
w.setInterval = (callback,delay) => {assert.equal(delay,3000); poll = callback; return 1;};
w.fetch = async (url,options) => {assert.equal(url,'/queue.json'); assert.equal(options.cache,'no-store'); if(disconnected) throw new Error('offline'); return {ok:true,json:async()=>JSON.parse(JSON.stringify(snapshot))};};
w.scrollTo = () => assert.fail('Polling must not scroll the page');
Object.defineProperty(w,'scrollY',{value:413});
const flush = () => new Promise(resolve=>setImmediate(resolve));
(async () => {
  w.eval(script);
  assert.equal($('emptyTitle').textContent,'Loading your queue');
  await flush();
  assert.equal($('jobs').children.length,3);
  assert.equal($('readyCount').textContent,'1');
  assert.equal($('attentionCount').textContent,'2');
  assert.equal(w.document.querySelectorAll('.job img').length,0,'Source text must not become markup');
  const first = $('jobs').children[0]; const notes = first.querySelector('.notes-link');
  assert.equal(notes.target,'_blank'); assert.equal(notes.rel,'noopener noreferrer');
  assert.equal(first.querySelector('.demo-link').textContent,'Open demo ↗');
  assert.match($('jobs').children[1].querySelector('.demo-link').textContent,/Preview · needs review/);
  assert.equal($('jobs').children[1].querySelector('.job-meta a').hasAttribute('href'),false);
  notes.focus(); assert.equal(w.document.activeElement,notes);
  await poll();
  assert.equal($('jobs').children[0],first); assert.equal(first.querySelector('.notes-link'),notes);
  assert.equal(w.document.activeElement,notes); assert.equal(w.scrollY,413);
  disconnected=true; await poll();
  assert.equal($('notice').hidden,false); assert.match($('notice').textContent,/last received jobs/);
  assert.equal(w.document.activeElement,notes); assert.equal($('jobs').children.length,3);
  disconnected=false;
  w.document.querySelector('[data-filter="ready"]').click();
  assert.equal(first.hidden,false); assert.equal($('jobs').children[1].hidden,true);
  snapshot.jobs[0].status='recorded'; snapshot.counts={recorded:1,built_pending_review:1,needs_build:1};
  await poll();
  assert.equal($('readyCount').textContent,'0'); assert.equal($('recordedCount').textContent,'1');
  assert.equal($('empty').hidden,false); assert.match($('emptyTitle').textContent,/No demos ready/);
  w.document.querySelector('[data-filter="recorded"]').click(); assert.equal(first.hidden,false);
  assert.equal($('total').textContent,'1 of 3 jobs');
  snapshot.jobs=[]; snapshot.counts={}; await poll();
  assert.equal($('jobs').children.length,0); assert.match($('emptyTitle').textContent,/No jobs/);
  assert.match($('emptyCopy').textContent,/Codex chat/);
  dom.window.close();
})().catch(error=>{console.error(error);dom.window.close();process.exitCode=1;});
"""
        result = subprocess.run([node, "-e", script], cwd=str(template),
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                universal_newlines=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
