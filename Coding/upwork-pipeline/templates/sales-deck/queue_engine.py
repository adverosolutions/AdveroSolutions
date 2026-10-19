#!/usr/bin/env python3
"""Durable local recording queue. No models, service calls or automatic approval.

Server contract: DEFAULT_ROOT is a Path; queue_root(root=None) returns the
absolute canonical root; public_snapshot(root=None) returns a JSON-safe dict
with schemaVersion, updatedAt, counts and ordered jobs. Each public job has id,
title, status, pageUrl and recordingScriptUrl; jobUrl/error are optional. URLs
are origin-relative. Registry, source paths, receipts and evidence are private.
main(argv=None) returns an integer exit code. queue_server.serve/start(root, port)
own server lifecycle; importing this module never starts a server.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit

import build as compiler
from schema import ValidationError, slug, text, validate

DEFAULT_ROOT = Path.home() / "Desktop/AdveroSolutions/Coding/upwork-pipeline/.local/recording-queue"
STATUSES = ("queued", "needs_build", "built_pending_review", "review_rejected",
            "reviewed_ready", "recorded", "failed")
REGISTRY = "registry.json"


def queue_root(root=None):
    return Path(DEFAULT_ROOT if root is None else root).expanduser().resolve()


def _now():
    return datetime.now(timezone.utc).isoformat()


def _no_symlinks(path, root):
    """Refuse links in private storage and generated paths before reading/writing."""
    for part in (path,) + tuple(path.parents):
        if part.is_symlink():
            raise ValidationError("queue storage cannot contain symbolic links")
        if part == root:
            break


@contextmanager
def _locked(root=None):
    root = queue_root(root)
    if root == Path(root.anchor) or root == Path.home().resolve():
        raise ValidationError("use an isolated queue root")
    root.mkdir(parents=True, exist_ok=True)
    lock = root / ".queue.lock"
    _no_symlinks(lock, root)
    fd = os.open(str(lock), os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "a+") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            path = root / REGISTRY
            _no_symlinks(path, root)
            if path.exists():
                registry = compiler.read_json(path)
                if (not isinstance(registry, dict) or registry.get("schemaVersion") != 1
                        or not isinstance(registry.get("jobs"), list)):
                    raise ValidationError("invalid queue registry; refusing to replace it")
            else:
                registry = {"schemaVersion": 1, "updatedAt": _now(), "jobs": []}
            yield root, registry
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _save(root, registry):
    registry["updatedAt"] = _now()
    compiler.atomic_text(root / REGISTRY, json.dumps(registry, indent=2, ensure_ascii=False) + "\n")
    os.chmod(str(root / REGISTRY), 0o600)
    # Persist the directory entry as well as the fsynced registry bytes.
    fd = os.open(str(root), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _out(root, entry):
    path = root / "public" / "jobs" / slug(entry["id"], "id")
    _no_symlinks(path, root)
    for name in compiler.OUTPUT_FILES + ("review-report.json",):
        _no_symlinks(path / name, root)
    return path


def _file_hash(path):
    return compiler.digest(Path(path).read_bytes())


def _identity(spec, out, report):
    """Bind raw spec, both generated files, build report and review receipt."""
    return {"specFileHash": _file_hash(spec), "pageHash": _file_hash(out / "page.html"),
            "scriptHash": _file_hash(out / "recording-script.txt"),
            "buildReportHash": _file_hash(out / "build-report.json"),
            "reviewReportHash": _file_hash(out / "review-report.json")
            if report["status"] != "built_pending_review" else None,
            "templateHash": report["templateHash"]}


def _inspect(root, entry, state, catalog):
    output = _out(root, entry)
    before = _file_hash(entry["spec"])
    report = compiler.reusable_report(entry["spec"], output, state, catalog)
    if report is None or report["id"] != entry["id"]:
        return None
    identity = _identity(entry["spec"], output, report)
    if identity["specFileHash"] != before or compiler.verify_lock() != state:
        return None
    return report, identity


def _invalidate(entry, error):
    entry.update(status="needs_build", error=error, invalidated=True)
    entry.pop("recording", None)


def _refresh(root, registry):
    try:
        state = compiler.verify_lock()
        catalog = compiler.read_json(compiler.ROOT / "platforms.json")
    except (OSError, ValueError, TypeError, AttributeError):
        state, catalog = None, None
    for entry in registry["jobs"]:
        if entry.get("generation") is None:
            try:
                spec_hash = _file_hash(entry["spec"])
            except FileNotFoundError:
                spec_hash = None
                for key in ("error", "buildError", "failedSpecHash", "privateError"):
                    entry.pop(key, None)
            except OSError:
                spec_hash = None
            if entry.get("buildError") and entry.get("failedSpecHash") == spec_hash:
                entry.update(status="failed", error=entry["buildError"])
            else:
                entry["status"] = "queued"
                entry.pop("error", None)
            continue
        if entry.get("invalidated"):
            _invalidate(entry, entry.get("error", "Artifacts changed; rebuild and review required."))
            continue
        if state is None:
            _invalidate(entry, "Template integrity check failed; rebuild and review required.")
            continue
        try:
            checked = _inspect(root, entry, state, catalog)
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            checked = None
        if checked is None or checked[1] != entry["generation"]:
            _invalidate(entry, "Spec or artifacts changed; rebuild and review required.")
            continue
        report, identity = checked
        receipt = entry.get("recording")
        if receipt and report["status"] == "reviewed_ready" and receipt.get("generation") == identity:
            entry["status"] = "recorded"
        else:
            entry.pop("recording", None)
            entry["status"] = report["status"]
        entry.pop("error", None)


def _job_url(value):
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > 2048 or any(ord(c) < 32 for c in value):
        raise ValidationError("jobUrl must be a public HTTP(S) URL")
    parsed = urlsplit(value)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
        raise ValidationError("jobUrl must be a public HTTP(S) URL")
    return value


def _snapshot(registry):
    jobs = []
    counts = {status: 0 for status in STATUSES}
    for entry in registry["jobs"]:
        status = entry["status"]
        counts[status] += 1
        links = status in ("built_pending_review", "review_rejected", "reviewed_ready", "recorded")
        prefix = "/jobs/" + entry["id"]
        job = {"id": entry["id"], "title": entry["title"], "status": status,
               "pageUrl": prefix + "/page.html" if links else None,
               "recordingScriptUrl": prefix + "/recording-script.txt" if links else None}
        if entry.get("jobUrl"):
            job["jobUrl"] = entry["jobUrl"]
        if entry.get("error"):
            job["error"] = entry["error"]
        jobs.append(job)
    return {"schemaVersion": 1, "updatedAt": registry["updatedAt"], "counts": counts, "jobs": jobs}


def public_snapshot(root=None):
    """Refresh under the same exclusive lock as every queue writer; allowlist data."""
    with _locked(root) as (root, registry):
        _refresh(root, registry)
        _save(root, registry)
        return _snapshot(registry)


def register(manifest, root=None):
    """Merge rows in registration order. Return (public_snapshot, safe_errors)."""
    manifest = Path(manifest).expanduser().resolve()
    data = compiler.read_json(manifest)
    if not isinstance(data, dict) or set(data) != {"jobs"} or not isinstance(data["jobs"], list):
        raise ValidationError("manifest must contain a jobs list")
    rows, errors, conflicts = {}, [], set()
    for position, row in enumerate(data["jobs"], 1):
        try:
            if not isinstance(row, dict) or set(row) - {"id", "title", "spec", "jobUrl"} or not {"id", "title", "spec"} <= set(row):
                raise ValidationError("each job needs id, title and spec")
            job_id = slug(row["id"], "id")
            title = text(row["title"], "title")
            if not isinstance(row["spec"], str) or not row["spec"].strip() or "\x00" in row["spec"]:
                raise ValidationError("spec must be a path")
            spec = Path(row["spec"]).expanduser()
            spec = (manifest.parent / spec).resolve() if not spec.is_absolute() else spec.resolve()
            entry = {"id": job_id, "title": title, "spec": str(spec), "jobUrl": _job_url(row.get("jobUrl")), "status": "queued"}
            if job_id in rows and _registration_key(rows[job_id]) != _registration_key(entry):
                conflicts.add(job_id)
            else:
                rows.setdefault(job_id, entry)
        except (OSError, ValueError, TypeError):
            errors.append("Row {}: invalid job registration.".format(position))
    with _locked(root) as (root, registry):
        existing = {entry["id"]: entry for entry in registry["jobs"]}
        archived = {entry["id"] for entry in registry.get("archivedJobs", [])}
        for job_id, entry in rows.items():
            if job_id in archived:
                errors.append(job_id + ": archived; restore it explicitly before registering again.")
            elif job_id in conflicts or job_id in existing and _registration_key(existing[job_id]) != _registration_key(entry):
                errors.append(job_id + ": conflicting registration; existing job preserved.")
            elif job_id not in existing:
                registry["jobs"].append(entry)
                existing[job_id] = entry
        _refresh(root, registry)
        _save(root, registry)
        return _snapshot(registry), errors


def _registration_key(entry):
    return entry["spec"], entry.get("jobUrl")


def build_jobs(ids=(), root=None):
    """Compile each selected job independently; return (public_snapshot, errors)."""
    errors = []
    with _locked(root) as (root, registry):
        _refresh(root, registry)
        existing = {entry["id"]: entry for entry in registry["jobs"]}
        chosen = list(dict.fromkeys(ids)) if ids else list(existing)
        for job_id in chosen:
            if job_id not in existing:
                errors.append("Unknown job: " + job_id)
                continue
            entry = existing[job_id]
            try:
                try:
                    before = _file_hash(entry["spec"])
                except FileNotFoundError:
                    # Registered specs may arrive later. Prior generations still
                    # require invalidation when their source disappears.
                    if entry.get("generation") is None:
                        continue
                    raise
                state = compiler.verify_lock()
                catalog = compiler.read_json(compiler.ROOT / "platforms.json")
                checked = _inspect(root, entry, state, catalog)
                if checked and not entry.get("invalidated") and checked[1] == entry.get("generation"):
                    continue
                output = _out(root, entry)
                normalized = validate(compiler.read_json(entry["spec"]), catalog)
                if normalized["id"] != job_id:
                    raise ValidationError("spec id must match canonical registered id")
                report = compiler.compile_job(entry["spec"], output, state, catalog)
                checked = _inspect(root, entry, state, catalog)
                if checked is None or checked[1]["specFileHash"] != before:
                    raise ValidationError("inputs changed during build; rebuild required")
                entry.update(status=report["status"], generation=checked[1])
                for key in ("invalidated", "recording", "error", "buildError", "failedSpecHash", "privateError"):
                    entry.pop(key, None)
            except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
                safe_error = "Build failed; check the private spec and template integrity."
                entry.update(status="failed", error=safe_error, buildError=safe_error, privateError=str(exc))
                try:
                    entry["failedSpecHash"] = _file_hash(entry["spec"])
                except OSError:
                    entry["failedSpecHash"] = None
                if entry.get("generation"):
                    _invalidate(entry, safe_error)
                errors.append(job_id + ": " + safe_error)
            # Each completed job is durable even if a later process is interrupted.
            _save(root, registry)
        _save(root, registry)
        return _snapshot(registry), errors


def _find(registry, job_id):
    slug(job_id, "id")
    for entry in registry["jobs"]:
        if entry["id"] == job_id:
            return entry
    raise ValidationError("unknown registered job")


def review(job_id, verdict, page_hash, notes, root=None):
    with _locked(root) as (root, registry):
        _refresh(root, registry)
        _save(root, registry)
        entry = _find(registry, job_id)
        if verdict not in ("approve", "reject"):
            raise ValidationError("verdict must be approve or reject")
        if entry["status"] not in ("built_pending_review", "review_rejected", "reviewed_ready", "recorded"):
            raise ValidationError("job must be built from current inputs before review")
        state = compiler.verify_lock()
        catalog = compiler.read_json(compiler.ROOT / "platforms.json")
        checked = _inspect(root, entry, state, catalog)
        if checked is None or checked[1] != entry["generation"]:
            raise ValidationError("inputs changed; rebuild before review")
        output = _out(root, entry)
        compiler.record_review(output, verdict, page_hash, notes, state)
        checked_after = _inspect(root, entry, state, catalog)
        if (checked_after is None or checked_after[1]["specFileHash"] != checked[1]["specFileHash"]
                or checked_after[1]["pageHash"] != checked[1]["pageHash"]
                or checked_after[1]["scriptHash"] != checked[1]["scriptHash"]):
            _invalidate(entry, "Inputs changed during review; rebuild and review required.")
            _save(root, registry)
            raise ValidationError("inputs changed during review")
        entry.update(status=checked_after[0]["status"], generation=checked_after[1])
        entry.pop("recording", None)
        entry.pop("error", None)
        _save(root, registry)
        return _snapshot(registry)


def recorded(job_id, loom=None, root=None):
    with _locked(root) as (root, registry):
        _refresh(root, registry)
        _save(root, registry)
        entry = _find(registry, job_id)
        if entry["status"] not in ("reviewed_ready", "recorded"):
            raise ValidationError("recording requires an approved exact current generation")
        entry["recording"] = {"recordedAt": _now(), "generation": dict(entry["generation"])}
        if loom is not None:
            entry["recording"]["loom"] = _job_url(loom)
        entry["status"] = "recorded"
        _save(root, registry)
        return _snapshot(registry)


def reopen(job_id, root=None):
    with _locked(root) as (root, registry):
        _refresh(root, registry)
        _save(root, registry)
        entry = _find(registry, job_id)
        entry.pop("recording", None)
        if entry["status"] == "recorded":
            entry["status"] = "reviewed_ready"
        _save(root, registry)
        return _snapshot(registry)


def archive(job_id, root=None):
    """Remove a finished/withdrawn job from the active board, preserving its files."""
    with _locked(root) as (root, registry):
        entry = _find(registry, job_id)
        archived = registry.setdefault("archivedJobs", [])
        if not isinstance(archived, list) or any(row["id"] == job_id for row in archived):
            raise ValidationError("invalid or conflicting archive; job preserved")
        entry["archivedAt"] = _now()
        registry["jobs"].remove(entry)
        archived.append(entry)
        _save(root, registry)
        return _snapshot(registry)


def restore(job_id, root=None):
    """Return an archived job to the board and recheck its generation identity."""
    slug(job_id, "id")
    with _locked(root) as (root, registry):
        if any(row["id"] == job_id for row in registry["jobs"]):
            raise ValidationError("job already active; existing job preserved")
        archived = registry.get("archivedJobs", [])
        entry = next((row for row in archived if row["id"] == job_id), None)
        if entry is None:
            raise ValidationError("unknown archived job")
        archived.remove(entry)
        entry.pop("archivedAt", None)
        registry["jobs"].append(entry)
        _refresh(root, registry)
        _save(root, registry)
        return _snapshot(registry)


def _print(snapshot, as_json=False):
    if as_json:
        print(json.dumps(snapshot, ensure_ascii=False))
    else:
        for job in snapshot["jobs"]:
            print("{}: {}{}".format(job["id"], job["status"], " — " + job["error"] if job.get("error") else ""))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("register", "build", "review", "status", "recorded", "reopen", "archive", "restore", "serve", "start"):
        sub = commands.add_parser(name)
        sub.add_argument("--root", default=argparse.SUPPRESS)
        if name == "register":
            sub.add_argument("manifest")
        elif name == "build":
            sub.add_argument("ids", nargs="*")
        elif name in ("review", "recorded", "reopen", "archive", "restore"):
            sub.add_argument("id")
        if name == "review":
            sub.add_argument("--verdict", choices=("approve", "reject"), required=True)
            sub.add_argument("--page-hash", required=True)
            sub.add_argument("--notes", required=True)
        elif name == "recorded":
            sub.add_argument("--loom")
        elif name == "status":
            sub.add_argument("--json", action="store_true")
        elif name in ("serve", "start"):
            sub.add_argument("--port", type=int, default=8769)
    args = parser.parse_args(argv)
    try:
        errors = []
        if args.command == "register":
            snapshot, errors = register(args.manifest, args.root)
        elif args.command == "build":
            snapshot, errors = build_jobs(args.ids, args.root)
        elif args.command == "review":
            snapshot = review(args.id, args.verdict, args.page_hash, args.notes, args.root)
        elif args.command == "recorded":
            snapshot = recorded(args.id, args.loom, args.root)
        elif args.command == "reopen":
            snapshot = reopen(args.id, args.root)
        elif args.command == "archive":
            snapshot = archive(args.id, args.root)
        elif args.command == "restore":
            snapshot = restore(args.id, args.root)
        elif args.command == "status":
            snapshot = public_snapshot(args.root)
        else:
            import queue_server
            result = getattr(queue_server, args.command)(queue_root(args.root), args.port)
            if isinstance(result, dict):
                print(json.dumps(result, ensure_ascii=False))
            return result if isinstance(result, int) else 0
        _print(snapshot, args.command == "status" and args.json)
        for error in errors:
            print(error, file=sys.stderr)
        return 1 if errors else 0
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        print("Error: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
