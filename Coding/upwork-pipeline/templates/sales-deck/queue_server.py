"""Read-only, loopback-only recording queue. Python 3.9 standard library."""
import argparse
import errno
import fcntl
import hashlib
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.parse import urlsplit

APP_ID = "advero-recording-queue"
DEFAULT_PORT = 8769
TEMPLATE_ROOT = Path(__file__).resolve().parent
ARTIFACT_ROUTE = re.compile(r"/jobs/([A-Za-z0-9][A-Za-z0-9_-]{0,127})/(page\.html|recording-script\.txt)\Z")


def _engine():
    return importlib.import_module("queue_engine")


def _root(root=None):
    return Path(_engine().queue_root(root)).resolve()


def _health(root):
    return {"app": APP_ID, "schemaVersion": 1,
            "rootDigest": hashlib.sha256(os.fsencode(str(root))).hexdigest()}


def _public_bytes(root, job_id, filename):
    """Open each component without following symlinks, even during replacement."""
    descriptors = []
    try:
        descriptor = os.open(str(root), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        descriptors.append(descriptor)
        for part in ("public", "jobs", job_id):
            descriptor = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                 dir_fd=descriptor)
            descriptors.append(descriptor)
        file_descriptor = os.open(filename, os.O_RDONLY | os.O_NOFOLLOW,
                                  dir_fd=descriptor)
        with os.fdopen(file_descriptor, "rb") as handle:
            return handle.read()
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _make_server(root=None, port=DEFAULT_PORT):
    canonical_root = _root(root)

    class Handler(BaseHTTPRequestHandler):
        server_version = APP_ID
        sys_version = ""

        def _respond(self, status, body, content_type="text/plain; charset=utf-8"):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; font-src 'self' data:; img-src data:; connect-src 'self'; base-uri 'none'; object-src 'none'; form-action 'none'; frame-ancestors 'none'")
            if status == 405:
                self.send_header("Allow", "GET, HEAD")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _json(self, status, data):
            self._respond(status, json.dumps(data, ensure_ascii=False).encode("utf-8"),
                          "application/json; charset=utf-8")

        def do_GET(self):
            port = self.server.server_address[1]
            if self.headers.get("Host") not in ("127.0.0.1:%s" % port, "localhost:%s" % port):
                self._respond(403, b"Local requests only.\n")
                return
            # Public routes have canonical ASCII spellings. Never decode a path.
            raw_target = self.requestline.split()[1]
            if raw_target != self.path or not self.path.startswith("/") or self.path.startswith("//") or "%" in self.path or "\\" in self.path or "#" in self.path:
                self._respond(404, b"Not found.\n")
                return
            path = urlsplit(self.path).path
            try:
                if path == "/health":
                    self._json(200, _health(canonical_root))
                elif path == "/":
                    self._respond(200, (TEMPLATE_ROOT / "queue.html").read_bytes(),
                                  "text/html; charset=utf-8")
                elif path == "/assets/inter-variable.woff2":
                    self._respond(200, (TEMPLATE_ROOT / "assets/inter-variable.woff2").read_bytes(),
                                  "font/woff2")
                elif path == "/queue.json":
                    self._json(200, _engine().public_snapshot(canonical_root))
                else:
                    match = ARTIFACT_ROUTE.fullmatch(path)
                    if not match:
                        self._respond(404, b"Not found.\n")
                        return
                    job_id, filename = match.groups()
                    key = "pageUrl" if filename == "page.html" else "recordingScriptUrl"
                    snapshot = _engine().public_snapshot(canonical_root)
                    authorized = any(job.get("id") == job_id and job.get(key) == path
                                     for job in snapshot.get("jobs", []))
                    if not authorized:
                        self._respond(404, b"Not found.\n")
                        return
                    body = _public_bytes(canonical_root, job_id, filename)
                    self._respond(200, body, "text/html; charset=utf-8" if filename == "page.html"
                                  else "text/plain; charset=utf-8")
            except (FileNotFoundError, NotADirectoryError, PermissionError, IsADirectoryError):
                self._respond(404, b"Not found.\n")
            except OSError as exc:
                # ELOOP is the expected result for a refused symbolic link.
                if exc.errno == errno.ELOOP:
                    self._respond(404, b"Not found.\n")
                else:
                    self.log_error("Queue read failed: %s", type(exc).__name__)
                    self._json(503, {"error": "Queue is unavailable. Retry shortly."})
            except Exception as exc:
                self.log_error("Queue snapshot failed: %s", type(exc).__name__)
                self._json(503, {"error": "Queue is unavailable. Retry shortly."})

        def do_HEAD(self):
            self.do_GET()

        def _unsupported(self):
            self.close_connection = True
            self._respond(405, b"Read-only queue. Use the engine CLI to make changes.\n")

        do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = _unsupported

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    return server


def serve(root=None, port=DEFAULT_PORT):
    """Run in the foreground. All queue mutations remain in the engine CLI."""
    with _make_server(root, port) as server:
        print("Recording queue: http://127.0.0.1:%s/" % server.server_address[1], flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


def _probe(port):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
    try:
        connection.request("GET", "/health")
        response = connection.getresponse()
        body = response.read(8193)
        if response.status != 200 or len(body) > 8192:
            return "occupied", None
        try:
            return "occupied", json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return "occupied", None
    except ConnectionRefusedError:
        return "free", None
    except (OSError, http.client.HTTPException):
        return "occupied", None
    finally:
        connection.close()


def start(root=None, port=DEFAULT_PORT):
    """Start a detached local process, or reuse this queue's healthy server."""
    if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
        raise ValueError("Port must be an integer from 1 to 65535.")
    canonical_root = _root(root)
    canonical_root.mkdir(parents=True, exist_ok=True)
    expected = _health(canonical_root)
    url = "http://127.0.0.1:%s/" % port
    # Serialize starts for one queue; no PID-file-based process termination.
    with (canonical_root / "server-start.lock").open("a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        state, health = _probe(port)
        if state == "occupied":
            if health == expected:
                return {"url": url, "reused": True}
            raise RuntimeError("Port %s is already in use by another service or queue; choose another port." % port)
        log_path = canonical_root / "server.log"
        with log_path.open("ab", buffering=0) as log:
            process = subprocess.Popen(
                [sys.executable, str(Path(__file__).resolve()), "serve", "--root", str(canonical_root), "--port", str(port)],
                stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                start_new_session=True, close_fds=True,
            )
        (canonical_root / "server.pid").write_text(str(process.pid) + "\n", encoding="ascii")
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            state, health = _probe(port)
            if health == expected:
                return {"url": url, "reused": False, "pid": process.pid}
            if state == "occupied":
                raise RuntimeError("Port %s became occupied; see the queue's server.log for diagnostics." % port)
            if process.poll() is not None:
                raise RuntimeError("Queue server did not start; see the queue's server.log for diagnostics.")
            time.sleep(0.1)
        raise RuntimeError("Queue server did not become healthy; see the queue's server.log and server.pid for diagnostics.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("serve", "start"))
    parser.add_argument("--root", type=Path)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()
    try:
        result = serve(args.root, args.port) if args.command == "serve" else start(args.root, args.port)
        if result is not None:
            print(json.dumps(result))
        return 0
    except (OSError, RuntimeError, ValueError) as exc:
        print("Queue server: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
