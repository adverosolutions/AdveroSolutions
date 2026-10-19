#!/usr/bin/env python3
"""Build a local reference board; no model calls, browser launch or queue writes."""
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent


def read(name):
    return json.loads((ROOT / name).read_text())


def main():
    sources = read("research/source-evidence.json")["sources"]
    data = {"catalog": read("catalog.json"), "references": read("references.json"),
            "demand": read("research/local-demand.json"), "publicDemand": read("research/public-demand.json"),
            "sources": [{k: s[k] for k in ("id", "platform", "surface", "url", "status")}
                        for s in sources]}
    ids = {source["id"] for source in sources}
    assert len({p["id"] for p in data["catalog"]["products"]}) == len(data["catalog"]["products"])
    for product in data["catalog"]["products"]:
        assert not product["productionReady"]
        assert set(product["sourceIds"]) <= ids, product["id"]
    for image in data["references"]["images"]:
        path = ROOT / image["path"]
        assert path.resolve().is_relative_to(ROOT.resolve())
        assert hashlib.sha256(path.read_bytes()).hexdigest() == image["sha256"], image["id"]
        assert urlsplit(image["sourcePage"]).scheme == "https", image["id"]
    # Only aggregate demand reaches the board; private local job paths stay in research evidence.
    data["demand"]["platforms"] = [{k: row[k] for k in ("platform", "jobs", "percent")}
                                    for row in data["demand"]["platforms"]]
    payload = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c").replace("&", "\\u0026")
    template = (ROOT / "board-template.html").read_text()
    assert template.count("__REFERENCE_DATA__") == 1
    output = template.replace("__REFERENCE_DATA__", payload)
    (ROOT / "index.html").write_text(output)
    print("Built", ROOT / "index.html")
    print(len(data["catalog"]["products"]), "plans;", len(data["references"]["images"]), "curated images; no production approval")


if __name__ == "__main__":
    main()
