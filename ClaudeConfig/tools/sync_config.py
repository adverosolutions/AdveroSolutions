#!/usr/bin/env python3
"""Audit or import local instruction files without deleting repository records.

The repository is the maintained source. Default: report differences only.
--import-new preserves missing instruction files. Existing differences require
--replace REPO_RELATIVE_PATH; each replacement is backed up under .tmp first.
No credentials, session logs, caches, or vendor application runtimes are imported.
"""
import argparse
from pathlib import Path
import re
import shutil
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
EXCLUDED = {"__pycache__", "node_modules", "synced", ".git", ".DS_Store"}
SECRET_NAMES = {"auth.json", "credentials.json", "token.json", "millionverifier-keys.md"}
SECRET_PATTERNS = [
    re.compile(rb"sk-ant-[A-Za-z0-9_-]{16,}"),
    re.compile(rb"(?<![A-Za-z])xai-[A-Za-z0-9]{24,}"),
    re.compile(rb"gh[pousr]_[A-Za-z0-9]{24,}"),
    re.compile(rb"AKIA[0-9A-Z]{16}"),
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(rb"Bearer[ \t]+[A-Za-z0-9._-]{32,}"),
]


def candidates(home, root):
    config = root / "ClaudeConfig"
    for src, dst in [
        (home / ".claude/skills", config / "skills"),
        (home / ".claude/agents", config / "agents"),
        (home / ".claude/scheduled-tasks", config / "scheduled-tasks"),
        (home / ".claude/projects/-Users-lorenzovillarreal-Desktop-AdveroSolutions/memory", config / "memory"),
    ]:
        if src.is_dir():
            for item in sorted(src.rglob("*")):
                rel = item.relative_to(src)
                if any(part.startswith(".") or part in EXCLUDED for part in rel.parts):
                    continue
                if item.is_file():
                    yield item, dst / rel
    src = home / ".claude/CLAUDE.md"
    if src.is_file():
        yield src, config / "global-CLAUDE.md"
    # Keep the two app-specific variants with their licenses and helper assets.
    for flavor, src in [("claude", home / ".claude/skills/synced"),
                        ("codex", home / ".agents/skills/synced")]:
        if src.is_dir():
            for item in sorted(src.rglob("*")):
                rel = item.relative_to(src)
                if any(part.startswith(".") or part == "__pycache__" for part in rel.parts):
                    continue
                if item.is_file():
                    yield item, config / "synced-skills" / flavor / rel


def synchronize(home, root, import_new=False, replacements=()):
    rows = []
    replace = set(replacements)
    pairs = list(candidates(home, root))
    eligible = set()
    for source, destination in pairs:
        rel = destination.relative_to(root).as_posix()
        if rel not in replace or source.name in SECRET_NAMES or not destination.exists():
            continue
        data = source.read_bytes()
        if not any(pattern.search(data) for pattern in SECRET_PATTERNS) and destination.read_bytes() != data:
            eligible.add(rel)
    unknown = replace - eligible
    if unknown:
        raise ValueError("--replace did not identify differing importable files: " + ", ".join(sorted(unknown)))
    used = set()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    for source, destination in pairs:
        rel = destination.relative_to(root).as_posix()
        if source.name in SECRET_NAMES:
            rows.append(("excluded-credential-record", rel))
            continue
        data = source.read_bytes()
        if any(pattern.search(data) for pattern in SECRET_PATTERNS):
            rows.append(("excluded-secret-pattern", rel))
            continue
        if destination.exists():
            if destination.read_bytes() == data:
                rows.append(("same", rel))
                continue
            if rel not in replace:
                rows.append(("conflict-kept-repo", rel))
                continue
            backup = root / ".tmp/config-import-backups" / stamp / rel
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(destination), str(backup))
            used.add(rel)
            status = "replaced-with-backup"
        else:
            if not import_new:
                rows.append(("missing-from-repo", rel))
                continue
            status = "imported"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        shutil.copymode(str(source), str(destination))
        rows.append((status, rel))
    unknown = replace - used
    if unknown:
        raise ValueError("--replace did not identify differing importable files: " + ", ".join(sorted(unknown)))
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", type=Path, default=Path.home())
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--import-new", action="store_true")
    parser.add_argument("--replace", action="append", default=[], metavar="REPO_RELATIVE_PATH")
    args = parser.parse_args(argv)
    try:
        rows = synchronize(args.home, args.root, args.import_new, args.replace)
    except ValueError as exc:
        parser.error(str(exc))
    for status, path in rows:
        if status != "same":
            print(status + "\t" + path)
    counts = {}
    for status, _ in rows:
        counts[status] = counts.get(status, 0) + 1
    print("Summary: " + ", ".join("%s=%d" % pair for pair in sorted(counts.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
