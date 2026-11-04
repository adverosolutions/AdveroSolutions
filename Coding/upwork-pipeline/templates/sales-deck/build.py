#!/usr/bin/env python3
"""Compile standalone sales demonstration pages. No service calls or model calls."""
import argparse
import base64
import hashlib
import html
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile

from schema import ValidationError, validate, public_job

ROOT = Path(__file__).resolve().parent
LOCK_FILES = ("schema.py", "native_schema.py", "gmail_schema.py", "funnel_schema.py", "product_schema.py", "intelligence_schema.py", "build.py", "runtime/shell.html", "runtime/base.css", "runtime/components.css", "runtime/platforms.css", "runtime/platforms.js", "runtime/native.js", "runtime/native.css", "runtime/gmail.js", "runtime/gmail.css", "runtime/funnel.js", "runtime/funnel.css", "runtime/intelligence.js", "runtime/intelligence.css", "runtime/product.js", "runtime/product.css", "runtime/architecture.js", "runtime/architecture.css", "runtime/cinematic.js", "runtime/cinematic.css", "runtime/app.js", "assets/inter-variable.woff2", "platforms.json")
OUTPUT_FILES = ("page.html", "recording-script.txt", "build-report.json")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(data):
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def read_json(path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValidationError("duplicate JSON key: " + key)
            result[key] = value
        return result
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=pairs,
                          parse_constant=lambda v: (_ for _ in ()).throw(ValidationError("nonfinite JSON number")))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValidationError("invalid JSON: " + str(exc))


def template_state():
    files = {name: digest((ROOT / name).read_bytes()) for name in LOCK_FILES}
    return {"schemaVersion": 1, "files": files, "templateHash": digest(canonical(files))}


def verify_lock():
    lock_path = ROOT / "template-lock.json"
    if not lock_path.is_file():
        raise ValidationError("template-lock.json missing; maintainer must finalize and lock the template")
    expected, actual = read_json(lock_path), template_state()
    if expected != actual:
        changed = [n for n in LOCK_FILES if expected.get("files", {}).get(n) != actual["files"][n]]
        raise ValidationError("template drift: " + ", ".join(changed) + "; requires maintainer review and lock")
    return actual


def safe_out(path):
    path = Path(os.path.abspath(os.fspath(path)))
    for parent in (path,) + tuple(path.parents):
        if parent.is_symlink():
            raise ValidationError("unsafe output path: symbolic links are not permitted")
    if path == Path(path.anchor) or path == Path.home() or path == ROOT or ROOT in path.parents and path.parts[len(ROOT.parts)] not in (".tmp",):
        raise ValidationError("unsafe output path: use an isolated job folder outside template sources")
    if path.exists() and not path.is_dir():
        raise ValidationError("output path is not a directory")
    for name in OUTPUT_FILES + ("review-report.json", "index.html", "batch-report.json"):
        if (path / name).is_symlink():
            raise ValidationError("unsafe output file: symbolic link")
    return path


def atomic_text(path, content):
    path = Path(path)
    if path.is_symlink():
        raise ValidationError("unsafe output file: symbolic link")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".deck-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def js_json(data):
    # JSON is data inside an inline script, never a script terminator or HTML.
    value = canonical(data).decode("utf-8")
    for old, new in (("&", "\\u0026"), ("<", "\\u003c"), (">", "\\u003e"), ("\u2028", "\\u2028"), ("\u2029", "\\u2029")):
        value = value.replace(old, new)
    return value


def page(job, catalog):
    css = "\n".join((ROOT / n).read_text(encoding="utf-8") for n in ("runtime/base.css", "runtime/platforms.css", "runtime/components.css", "runtime/native.css", "runtime/intelligence.css", "runtime/gmail.css", "runtime/funnel.css", "runtime/product.css", "runtime/architecture.css", "runtime/cinematic.css"))
    script = "const PLATFORM_CATALOG=" + js_json(catalog) + ";\nconst DATA=" + js_json(job) + ";\n"
    company = job["account"]["name"].strip() or "your team"
    motion_config = {"company": company, "recipient": job.get("personalization", {}).get("firstName") or company,
                     "initials": job["account"]["initials"], "systemName": job["systemName"], "steps": job["cover"]["previewSteps"]}
    script += "window.MotionConfig=" + js_json(motion_config) + ";\n"
    script += "\n".join((ROOT / n).read_text(encoding="utf-8") for n in ("runtime/platforms.js", "runtime/native.js", "runtime/intelligence.js", "runtime/gmail.js", "runtime/funnel.js", "runtime/product.js", "runtime/architecture.js", "runtime/cinematic.js", "runtime/app.js"))
    font = base64.b64encode((ROOT / "assets/inter-variable.woff2").read_bytes()).decode("ascii")
    replacements = {"__PAGE_TITLE__": html.escape(job["title"], quote=True), "__INLINE_CSS__": css, "__INLINE_JS__": script, "__INLINE_FONT__": font}
    shell = (ROOT / "runtime/shell.html").read_text(encoding="utf-8")
    for marker in replacements:
        if shell.count(marker) != 1:
            raise ValidationError("shell must contain exactly one " + marker)
    # Single substitution against shell only: payload cannot accidentally expand sentinels.
    return re.sub(r"__PAGE_TITLE__|__INLINE_CSS__|__INLINE_JS__|__INLINE_FONT__", lambda m: replacements[m.group()], shell)


def recording(job):
    lines = [job["title"], "Sales demonstration. Illustrative sample; no live integration claim.",
             "Quick and Standard: required scenes. Detailed: all scenes.", "Chapters advance manually. Replay holds the result.\n"]
    for scene in [dict(job["cover"], id="cover")] + job["scenes"] + [dict(job["close"], id="close")]:
        lines.append("{}{}\n{}".format(scene["id"], " (Detailed only)" if scene.get("optional") else "", scene["beat"]))
        details = scene.get("details", scene.get("anchors", []))
        if scene["id"] == "close":
            details = [m["name"] + ": " + m["definition"] for m in scene["metrics"]]
        lines.extend("- " + d for d in details)
        lines.append("")
    return "\n".join(lines)


def compile_job(spec_path, out, state, catalog=None):
    if template_state() != state:
        raise ValidationError("template changed during generation; requires maintainer review and lock")
    catalog = read_json(ROOT / "platforms.json") if catalog is None else catalog
    normalized = validate(read_json(spec_path), catalog)
    public = public_job(normalized)
    output = safe_out(out)
    page_text, script = page(public, catalog), recording(public)
    if template_state() != state:
        raise ValidationError("template changed during generation; discard candidate and rebuild")
    report = {"schemaVersion": 1, "id": public["id"], "title": public["title"], "status": "built_pending_review", "visualReview": "pending",
              "contentHash": digest(canonical(public)), "specHash": digest(canonical(normalized)),
              "templateHash": state["templateHash"], "files": {"page.html": digest(page_text.encode("utf-8")), "recording-script.txt": digest(script.encode("utf-8"))}}
    # Stage complete files first. Replace each atomically, commit report last. Readers
    # trust report only after checking its file hashes; unrelated job files survive.
    output.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".deck-stage-", dir=str(output)))
    try:
        for name, value in (("page.html", page_text), ("recording-script.txt", script), ("build-report.json", json.dumps(report, indent=2) + "\n")):
            (stage / name).write_text(value, encoding="utf-8")
        for name in OUTPUT_FILES:
            os.replace(stage / name, output / name)
    finally:
        shutil.rmtree(stage)
    review_path = output / "review-report.json"
    if review_path.exists():
        if review_path.is_symlink():
            raise ValidationError("unsafe review report path")
        review_path.unlink()
    parent = output.parent / "batch-report.json"
    if output.name == report["id"] and parent.is_file():
        batch_report = read_json(parent)
        matched = False
        for entry in batch_report.get("jobs", []):
            if entry.get("id") == report["id"]:
                entry.update(status="built_pending_review", visualReview="pending",
                             contentHash=report["contentHash"], title=report["title"], reused=False)
                entry.pop("pageHash", None)
                entry.pop("error", None)
                matched = True
        if matched:
            jobs = batch_report.get("jobs", [])
            batch_report["status"] = "failed" if any(e["status"] == "failed" for e in jobs) else "building" if any(e["status"] == "queued" for e in jobs) else "review_rejected" if any(e["status"] == "review_rejected" for e in jobs) else "built_pending_review"
            atomic_text(parent, json.dumps(batch_report, indent=2) + "\n")
            atomic_text(output.parent / "index.html", batch_index(jobs))
    return report


def batch_index(entries):
    labels = {"built_pending_review": "Needs review", "reviewed_ready": "Ready to record", "review_rejected": "Needs repair", "queued": "Queued", "failed": "Build failed"}
    items = []
    for e in entries:
        label = html.escape(e.get("title", e.get("id", "Job {}".format(e["position"]))))
        if e["status"] in ("built_pending_review", "reviewed_ready", "review_rejected"):
            label = '<a href="{}/page.html">{}</a>'.format(e["id"], label)
        items.append('<li><div>{}</div><span class="status {}">{}</span>{}</li>'.format(label, e["status"], labels[e["status"]], '<p>' + html.escape(e["error"]) + '</p>' if "error" in e else ""))
    ready = sum(e["status"] == "reviewed_ready" for e in entries)
    pending = sum(e["status"] == "built_pending_review" for e in entries)
    return '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Recording queue</title><style>body{margin:0;background:#f5f7fb;color:#172844;font:16px system-ui,sans-serif}main{max-width:900px;margin:48px auto;padding:0 20px}h1{font-size:32px}ol{padding:0;list-style:none}li{background:white;border:1px solid #e4eaf3;border-radius:14px;padding:20px;margin:12px 0;display:flex;flex-wrap:wrap;gap:14px;align-items:center}li div{flex:1;min-width:180px}a{color:#1858d9;text-decoration:none}a:hover{text-decoration:underline}.status{font-size:13px;padding:6px 10px;border-radius:8px;background:#edf2fa;color:#405375}.reviewed_ready{background:#e6f3ec;color:#267346}.failed,.review_rejected{background:#fff0ed;color:#993e32}li p{width:100%;margin:0;font-size:14px}</style><body><main><h1>Recording queue</h1><p>' + str(ready) + ' ready to record · ' + str(pending) + ' need review</p><ol>' + "".join(items) + "</ol></main></body></html>"


def reusable_report(spec_path, out, state, catalog):
    """Reuse only a fully hash-consistent exact generation and review receipt."""
    normalized = validate(read_json(spec_path), catalog)
    output = safe_out(out)
    try:
        report = read_json(output / "build-report.json")
        if report.get("id") != normalized["id"] or report.get("specHash") != digest(canonical(normalized)) or report.get("contentHash") != digest(canonical(public_job(normalized))) or report.get("templateHash") != state["templateHash"]:
            return None
        for name in ("page.html", "recording-script.txt"):
            if digest((output / name).read_bytes()) != report.get("files", {}).get(name):
                return None
        if report.get("status") in ("reviewed_ready", "review_rejected"):
            review = read_json(output / "review-report.json")
            expected = "approve" if report["status"] == "reviewed_ready" else "reject"
            if review.get("verdict") != expected or report.get("visualReview") != expected or review.get("status") != report["status"] or review.get("id") != report["id"] or review.get("pageHash") != report["files"]["page.html"] or review.get("contentHash") != report["contentHash"] or review.get("templateHash") != state["templateHash"]:
                return None
        elif report.get("status") != "built_pending_review" or report.get("visualReview") != "pending":
            return None
        return report
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None


def batch(manifest, out, state, resume=False):
    data = read_json(manifest)
    if not isinstance(data, dict) or set(data) != {"jobs"} or not isinstance(data["jobs"], list) or not data["jobs"]:
        raise ValidationError("manifest must be {jobs: [relativeSpecPath, ...]}")
    output = safe_out(out)
    catalog, entries, slug_counts = read_json(ROOT / "platforms.json"), [], {}
    base = Path(manifest).resolve().parent
    # Preflight every slug so every duplicate is failed, with no overwritten page.
    for i, item in enumerate(data["jobs"], 1):
        entry = {"position": i, "status": "queued"}
        try:
            if not isinstance(item, str) or not item or Path(item).is_absolute() or ".." in Path(item).parts:
                raise ValidationError("manifest spec paths must be relative and contained in manifest folder")
            source = base / item
            if base not in source.resolve().parents:
                raise ValidationError("manifest path escapes its folder")
            entry["spec"] = source
            from schema import slug
            raw = read_json(source)
            entry["id"] = slug(raw.get("id"), "id")
            if isinstance(raw.get("title"), str):
                entry["title"] = raw["title"][:240]
            slug_counts[entry["id"]] = slug_counts.get(entry["id"], 0) + 1
        except (OSError, ValueError, AttributeError) as exc:
            entry.update(status="failed", error=str(exc))
        entries.append(entry)
    for e in entries:
        if "id" in e and slug_counts[e["id"]] > 1:
            e.update(status="failed", error="duplicate slug in manifest")
    def publish():
        public = [{k: v for k, v in e.items() if k != "spec"} for e in entries]
        report = {"schemaVersion": 1, "status": "failed" if any(e["status"] == "failed" for e in entries) else "building" if any(e["status"] == "queued" for e in entries) else "reviewed_ready" if all(e["status"] == "reviewed_ready" for e in entries) else "review_rejected" if any(e["status"] == "review_rejected" for e in entries) else "built_pending_review", "templateHash": state["templateHash"], "jobs": public}
        atomic_text(output / "index.html", batch_index(public))
        atomic_text(output / "batch-report.json", json.dumps(report, indent=2) + "\n")
    publish()
    for e in entries:
        if e["status"] == "queued":
            try:
                report = reusable_report(e["spec"], output / e["id"], state, catalog) if resume else None
                reused = report is not None
                if report is None:
                    report = compile_job(e["spec"], output / e["id"], state, catalog)
                e.update(status=report["status"], contentHash=report["contentHash"], title=report["title"], reused=reused)
                if report["visualReview"] != "pending":
                    e.update(visualReview=report["visualReview"], pageHash=report["files"]["page.html"])
            except (OSError, ValueError) as exc:
                e.update(status="failed", error=str(exc))
            publish()
        print("{}: {}".format(e.get("id", e["position"]), e["status"]), flush=True)
    return 1 if any(e["status"] == "failed" for e in entries) else 0


def record_review(out, verdict, page_hash, notes, state):
    output = safe_out(out)
    report = read_json(output / "build-report.json")
    if report.get("templateHash") != state["templateHash"]:
        raise ValidationError("build template differs from current locked template; rebuild before review")
    if not re.fullmatch(r"[0-9a-f]{64}", page_hash):
        raise ValidationError("page-hash must be a SHA-256 hex digest")
    if digest((output / "page.html").read_bytes()) != page_hash or report.get("files", {}).get("page.html") != page_hash:
        raise ValidationError("review page-hash does not match the current built page")
    if digest((output / "recording-script.txt").read_bytes()) != report.get("files", {}).get("recording-script.txt"):
        raise ValidationError("recording script changed since build")
    if not notes.strip() or len(notes) > 4000:
        raise ValidationError("review notes must contain 1..4000 characters")
    status = "reviewed_ready" if verdict == "approve" else "review_rejected"
    review = {"schemaVersion": 1, "id": report["id"], "verdict": verdict, "status": status,
              "pageHash": page_hash, "contentHash": report["contentHash"], "templateHash": report["templateHash"], "notes": notes.strip()}
    # This records the independent reviewer's supplied verdict; it performs no visual review.
    atomic_text(output / "review-report.json", json.dumps(review, indent=2) + "\n")
    report.update(status=status, visualReview=verdict)
    atomic_text(output / "build-report.json", json.dumps(report, indent=2) + "\n")
    parent = output.parent / "batch-report.json"
    if parent.is_file():
        batch_report = read_json(parent)
        for entry in batch_report.get("jobs", []):
            if entry.get("id") == report["id"] and entry.get("contentHash") == report["contentHash"]:
                entry.update(status=status, visualReview=verdict, pageHash=page_hash)
        jobs = batch_report.get("jobs", [])
        batch_report["status"] = "reviewed_ready" if jobs and all(e["status"] == "reviewed_ready" for e in jobs) else "review_rejected" if any(e["status"] == "review_rejected" for e in jobs) else "failed" if any(e["status"] == "failed" for e in jobs) else "built_pending_review"
        atomic_text(parent, json.dumps(batch_report, indent=2) + "\n")
        atomic_text(output.parent / "index.html", batch_index(jobs))
    return review


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "build", "batch"):
        sub = commands.add_parser(name)
        sub.add_argument("spec")
        if name != "validate":
            sub.add_argument("--out", required=True)
        if name == "batch":
            sub.add_argument("--resume", action="store_true", help="reuse unchanged hash-consistent pages and review receipts")
    commands.add_parser("lock", help="maintainer only: record accepted shared template files")
    review = commands.add_parser("record-review", help="main only: record an independent visual review of the exact page")
    review.add_argument("directory")
    review.add_argument("--verdict", choices=("approve", "reject"), required=True)
    review.add_argument("--page-hash", required=True)
    review.add_argument("--notes", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "lock":
            atomic_text(ROOT / "template-lock.json", json.dumps(template_state(), indent=2, sort_keys=True) + "\n")
            print("Template locked. This is an integrity check, not a security boundary.")
            return 0
        state = verify_lock()
        if args.command == "record-review":
            report = record_review(args.directory, args.verdict, args.page_hash, args.notes, state)
            print(report["id"] + ": " + report["status"])
        elif args.command == "validate":
            job = validate(read_json(args.spec), read_json(ROOT / "platforms.json"))
            print(job["id"] + ": valid")
        elif args.command == "build":
            report = compile_job(args.spec, args.out, state)
            print(report["id"] + ": " + report["status"])
        else:
            return batch(args.spec, args.out, state, args.resume)
        return 0
    except (OSError, ValueError) as exc:
        print("Error: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
