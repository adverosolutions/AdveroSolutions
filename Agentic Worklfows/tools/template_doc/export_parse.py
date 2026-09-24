"""Read jobs/approve_templates.py --export markdown into entries.

Each entry: id, section, meta {key: value}, approvable, sha256, main (list of
lines, blank edges stripped) and variants [{name, desc, lines}].
Reading only. Python 3.9.
"""
import re
from typing import Any, Dict, List

VARIANT_RE = re.compile(r"^=== variant: (\S+) \((.*)\) ===$")


def strip_blank(ls):
    ls = list(ls)
    while ls and not ls[-1].strip():
        ls.pop()
    while ls and not ls[0].strip():
        ls.pop(0)
    return ls


def split_variants(text_lines):
    main, variants = [], []
    for ln in text_lines:
        m = VARIANT_RE.match(ln)
        if m:
            variants.append({"name": m.group(1), "desc": m.group(2), "lines": []})
            continue
        (variants[-1]["lines"] if variants else main).append(ln)
    for v in variants:
        v["lines"] = strip_blank(v["lines"])
    return strip_blank(main), variants


def parse_export(path: str) -> Dict[str, Any]:
    lines = open(path, encoding="utf-8").read().split("\n")
    sections = []  # type: List[Dict[str, Any]]
    entries = []  # type: List[Dict[str, Any]]
    cur = None
    entry = None
    in_text = False
    for ln in lines:
        if in_text:
            if ln == "```":
                in_text = False
            else:
                entry["text"].append(ln)
            continue
        if ln.startswith("## "):
            cur = {"title": ln[3:], "prose": [], "entries": []}
            sections.append(cur)
            entry = None
            continue
        m = re.match(r"^### `(.+)`$", ln)
        if m and cur is not None:
            entry = {"id": m.group(1), "section": cur["title"], "meta": {}, "text": [],
                     "approvable": False, "sha256": None, "reference_only": False}
            cur["entries"].append(entry)
            entries.append(entry)
            continue
        if ln.startswith("```text") and entry is not None:
            in_text = True
            continue
        if entry is not None:
            if ln.startswith("<!-- approve-template"):
                entry["approvable"] = True
                mm = re.search(r"sha256=([0-9a-f]+)", ln)
                entry["sha256"] = mm.group(1) if mm else None
            elif ln.startswith("- "):
                body = ln[2:]
                if ":" in body:
                    k, v = body.split(":", 1)
                    entry["meta"][k.strip()] = v.strip()
                if body.startswith("reference only"):
                    entry["reference_only"] = True
        elif cur is not None and ln.strip():
            cur["prose"].append(ln)
    for e in entries:
        e["main"], e["variants"] = split_variants(e["text"])
    counts = {}
    for s in sections:
        if s["title"] == "Counts":
            for p in s["prose"]:
                mm = re.match(r"^- (\w+): (\d+)$", p)
                if mm:
                    counts[mm.group(1)] = int(mm.group(2))
    return {"sections": sections, "entries": entries, "counts": counts,
            "header": lines[:15]}


def variant(entry, name):
    for v in entry["variants"]:
        if v["name"] == name:
            return v
    return None


def source_of(entry):
    return entry["meta"].get("source", "").strip("`")
