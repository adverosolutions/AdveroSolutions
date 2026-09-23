#!/usr/bin/env python3
"""Second pass for Tier-2 candidates whose fetched text came back thin
(< 300 useful chars: JS-rendered home page, CSS-only, redirect to http, etc.).

  python3 personalize/refetch_thin.py <batch_dir>

Tries harder: http:// fallback, common about-page paths, aggressive CSS/JS
stripping, and a text-density filter. Rewrites <lead_id>.txt when it finds
more; demotes the lead to TIER1_ONLY in leads.json when it still cannot.
"""
import json, re, ssl, sys, urllib.request, urllib.parse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
      "Accept": "text/html,*/*;q=0.8", "Accept-Language": "en-US,en;q=0.9"}
ABOUT_PATHS = ["/about", "/about-us", "/about-us/", "/aboutus", "/our-story", "/who-we-are", "/company", "/about.html"]
MIN, MAX = 300, 2500


def clean_text(html):
    html = re.sub(r"(?is)<(script|style|noscript|svg|iframe|template).*?</\1>", " ", html)
    html = re.sub(r"(?is)<!--.*?-->", " ", html)
    txt = re.sub(r"(?s)<[^>]+>", "\n", html)
    txt = re.sub(r"&[a-z#0-9]+;", " ", txt)
    keep = []
    for line in txt.splitlines():
        s = line.strip()
        if len(s) < 3: continue
        if s.count("{") + s.count("}") + s.count(";") > 3: continue          # leftover CSS
        if re.match(r"^[\w\-\.]+\s*:\s*[^\s]+;?$", s): continue               # css prop
        if len(re.findall(r"[A-Za-z]{3,}", s)) < 2: continue                   # no words
        keep.append(s)
    return re.sub(r"\s+", " ", " ".join(keep)).strip()


def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=15, context=ctx) as r:
        return r.geturl(), r.read(500000).decode("utf-8", "ignore")


def harder(site):
    site = site.strip()
    if not site.startswith("http"): site = "https://" + site
    bases = [site, site.replace("https://", "http://", 1)]
    parts, urls = [], []
    for b in bases:
        try:
            u, h = get(b); t = clean_text(h)
            if len(t) >= MIN:
                parts.append(f"[HOME {u}]\n{t[:MAX]}"); urls.append(u); site = u; break
        except Exception:
            continue
    for p in ABOUT_PATHS:
        try:
            u, h = get(urllib.parse.urljoin(site, p)); t = clean_text(h)
            if len(t) >= MIN and u not in urls:
                parts.append(f"\n\n[ABOUT {u}]\n{t[:MAX]}"); urls.append(u); break
        except Exception:
            continue
    return "\n".join(parts), urls


def main():
    bdir = Path(sys.argv[1])
    leads = json.loads((bdir / "leads.json").read_text())
    thin = [l for l in leads if l["route"] == "TIER2_CANDIDATE" and
            (not l["text_file"] or len(clean_text((bdir / l["text_file"]).read_text())) < MIN)]
    print(f"[refetch] {len(thin)} thin of {sum(1 for l in leads if l['route']=='TIER2_CANDIDATE')} tier-2 candidates")
    with ThreadPoolExecutor(12) as ex:
        res = list(ex.map(lambda l: harder(l["company_website"]), thin))
    fixed = 0
    for l, (txt, urls) in zip(thin, res):
        if txt:
            (bdir / f"{l['lead_id']}.txt").write_text(txt); l["text_file"] = f"{l['lead_id']}.txt"; l["source_urls"] = urls; fixed += 1
        else:
            l["route"] = "TIER1_ONLY"; l["text_file"] = ""
    (bdir / "leads.json").write_text(json.dumps(leads, indent=1))
    print(f"[refetch] recovered {fixed}, demoted {len(thin)-fixed} to TIER1_ONLY")


if __name__ == "__main__":
    main()
