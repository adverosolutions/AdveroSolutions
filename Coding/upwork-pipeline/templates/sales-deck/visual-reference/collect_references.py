#!/usr/bin/env python3
"""Collect public vendor reference images; never signs in or executes page code.

Run with the bundled workspace Python (Pillow is used only to inspect dimensions).
Downloaded images remain original bytes. Selection is a candidate list, not visual
approval: a maintainer must classify screenshots and reject logos/marketing art.
"""
import concurrent.futures
import hashlib
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import re
import urllib.parse
import urllib.request

from PIL import Image

ROOT = Path(__file__).resolve().parent
HEADERS = {"User-Agent": "AdveroSolutions-Visual-Reference/1.0 (public documentation research)"}
MAX_BYTES = 5 * 1024 * 1024


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.images = []
        self.links = []
        self.title = []
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "title":
            self.in_title = True
        if tag == "a" and attrs.get("href"):
            self.links.append(attrs["href"])
        if tag in ("img", "source"):
            alt = attrs.get("alt", "")
            values = [attrs.get(k) for k in ("src", "data-src", "data-original", "data-lazy-src")]
            srcset = attrs.get("srcset") or attrs.get("data-srcset")
            if srcset:
                values.append(srcset.split(",")[-1].strip().split(" ")[0])
            for value in values:
                if value and not value.startswith("data:"):
                    self.images.append({"url": value, "alt": alt})

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False

    def handle_data(self, text):
        if self.in_title:
            self.title.append(text)


def get(url):
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=22) as response:
        data = response.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError("asset over 5 MiB")
        return data, response.geturl(), response.headers.get("Content-Type", "")


def collect(source):
    result = dict(source, checkedAt="2026-10-19", images=[], candidates=[], links=[])
    try:
        data, final_url, content_type = get(source["url"])
        if "html" not in content_type:
            raise ValueError("source is not an HTML page")
        page = Page()
        page.feed(data.decode("utf-8", errors="replace"))
        result.update(status="fetched", finalUrl=final_url, title="".join(page.title).strip())
        result["links"] = list(dict.fromkeys(urllib.parse.urljoin(final_url, value) for value in page.links
                                             if not value.startswith(("#", "mailto:", "javascript:"))))[:150]
        candidates = []
        seen = set()
        for item in page.images:
            url = urllib.parse.urljoin(final_url, item["url"])
            if url in seen or urllib.parse.urlsplit(url).scheme not in ("http", "https"):
                continue
            seen.add(url)
            if re.search(r"logo|favicon|avatar|pixel|badge|/icons/|\.svg(?:\?|$)", url + " " + item["alt"], re.I):
                continue
            candidates.append(dict(item, url=url))
        result["candidates"] = candidates
        for item in candidates[:30]:
            if len(result["images"]) >= 3:
                break
            try:
                image_data, image_url, mime = get(item["url"])
                with Image.open(io.BytesIO(image_data)) as image:
                    width, height = image.size
                    fmt = image.format
                if width < 200 or height < 110 or width * height < 30000 or fmt not in ("PNG", "JPEG", "WEBP", "GIF"):
                    continue
                digest = hashlib.sha256(image_data).hexdigest()
                if any(asset["sha256"] == digest for asset in result["images"]):
                    continue
                suffix = {"PNG": "png", "JPEG": "jpg", "WEBP": "webp", "GIF": "gif"}[fmt]
                path = ROOT / "assets" / (source["id"] + "-" + digest[:12] + "." + suffix)
                path.write_bytes(image_data)
                result["images"].append({"path": str(path.relative_to(ROOT)), "url": image_url,
                                         "sourcePage": source["url"], "alt": item["alt"],
                                         "width": width, "height": height, "sha256": digest,
                                         "bytes": len(image_data), "classification": "unreviewed-candidate"})
            except Exception:
                continue
    except Exception as error:
        result.update(status="unavailable", error=type(error).__name__ + ": " + str(error)[:180])
    return result


def main():
    sources = json.loads((ROOT / "research/sources.json").read_text())["sources"]
    (ROOT / "assets").mkdir(exist_ok=True)
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        for result in pool.map(collect, sources):
            results.append(result)
            print(result["id"], result["status"], "images=" + str(len(result["images"])), flush=True)
    (ROOT / "research/source-evidence.json").write_text(json.dumps({"asOf": "2026-10-19", "sources": results}, indent=2) + "\n")


if __name__ == "__main__":
    main()
