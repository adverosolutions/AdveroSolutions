#!/usr/bin/env python3
"""Offline checks for business-skill discovery, current references and source hashes."""
from pathlib import Path
import csv
import hashlib
import re

ROOT = Path(__file__).resolve().parents[2]


def check(root=ROOT):
    skills = sorted((root / "ClaudeConfig/skills").glob("*/SKILL.md"))
    assert len(skills) == 25, "business skill count changed; review the inventory"
    for path in skills:
        assert (root / ".agents/skills" / path.parent.name / "SKILL.md").resolve() == path.resolve(), str(path)
        text = path.read_text()
        section = text.split("Current sources:", 1)[1].split("\n\n\n", 1)[0]
        section += text.split("Current sources:", 1)[0]
        for target in re.findall(r"\]\(([^)]+)\)", section):
            if not target.startswith(("http", "/", "#")):
                assert (path.parent / target).exists(), "%s: %s" % (path, target)
    count = 0
    for manifest in (root / "ClaudeConfig/grok-source/2026-11-04").glob("*-export/MANIFEST.tsv"):
        with manifest.open() as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                path = manifest.parent / row["path"]
                data = path.read_bytes()
                assert len(data) == int(row["bytes"]), str(path)
                assert hashlib.sha256(data).hexdigest() == row["sha256"], str(path)
                count += 1
    print("25 business skills: discovery and current references passed; %d exported source hashes passed." % count)


if __name__ == "__main__":
    check()
