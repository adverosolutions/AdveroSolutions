#!/usr/bin/env python3
"""Recount named tools in original, deduplicated Upwork posts in this repo."""
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
JOBS = ROOT.parents[2] / "jobs"


def main():
    destination = ROOT / "research/local-demand.json"
    patterns = json.loads(destination.read_text())["patterns"]
    unique = {}
    excluded = 0
    for path in JOBS.rglob("jd.txt"):
        if any(part.startswith("_") or part in (".tmp", ".stale")
               for part in path.relative_to(JOBS).parts):
            continue
        raw = path.read_text(errors="replace")
        match = re.search(r"^url:\s*(\S+)", raw, re.M | re.I)
        url = match.group(1).split("?")[0].rstrip("/") if match else ""
        parsed = urlsplit(url)
        if parsed.hostname not in ("upwork.com", "www.upwork.com"):
            excluded += 1
            continue
        identity = re.search(r"~(?:02)?([0-9]{15,})", parsed.path)
        key = identity.group(1) if identity else url
        body = raw.split("\n\n", 1)[-1]
        title = raw.splitlines()[1] if len(raw.splitlines()) > 1 else ""
        row = {"path": str(path.relative_to(JOBS.parent)), "mtime": path.stat().st_mtime,
               "text": title + "\n" + body, "url": url}
        if key not in unique or row["mtime"] > unique[key]["mtime"]:
            unique[key] = row
    rows = []
    for platform, pattern in patterns.items():
        matches = [{"path": row["path"], "url": row["url"]}
                   for row in unique.values() if re.search(pattern, row["text"], re.I | re.S)]
        rows.append({"platform": platform, "jobs": len(matches),
                     "percent": round(100 * len(matches) / len(unique), 1), "evidence": matches})
    rows.sort(key=lambda row: (-row["jobs"], row["platform"]))
    output = {"asOf": "2026-10-19", "scope": "Original repository job posts with real Upwork URLs; selected historical corpus, not all Upwork",
              "uniqueJobs": len(unique), "excludedWithoutUpworkUrl": excluded,
              "method": "Deduplicate canonical numeric Upwork job ID or normalized URL. Count each platform once per original title/body; exclude metadata and example folders. Mentions overlap. Only explicit Make.com, Integromat or automation/scenario aliases are counted, so bare Make is conservatively undercounted. Claude Skills uses a 35-character co-occurrence window and is a provisional subcategory. No temporal or market-wide prevalence claim.",
              "patterns": patterns, "platforms": rows}
    destination.write_text(json.dumps(output, indent=2) + "\n")
    print("Unique Upwork jobs:", len(unique), "Excluded without Upwork URL:", excluded)
    for row in rows[:18]:
        print(row["platform"], row["jobs"], str(row["percent"]) + "%")


if __name__ == "__main__":
    main()
