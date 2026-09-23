#!/usr/bin/env python3
"""Step 1 of a daily run: pick the next N leads in send order, fetch+trim their
pages, and stage a batch folder for the extraction subagent.

  python3 personalize/daily_pick.py --n 300 [--only-clean] [--niche recruiting]

Writes personalize/batches/<batch_id>/leads.json and one <lead_id>.txt per
Tier-2 candidate (home + about page text, trimmed). Marks picked rows "queued"
in the sheet, and off-niche rows "skipped" right away.
"""
import argparse, csv, json, re, ssl, time, urllib.request, urllib.error, socket
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
import gspread
from sheet_io import open_tab, ROOT

SHEET_ID = "1OWJP1WZIFXUi6fIx_QgeUU-KmLqiK5ZsRo2O61BWsMw"
PRE = ROOT / "personalize" / "precheck.csv"
BATCHES = ROOT / "personalize" / "batches"
ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
MAX_CHARS = 2500


def fetch(url, timeout=12):
    if not url.startswith("http"): url = "https://" + url
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Macintosh) AppleWebKit/537.36 Chrome/120 Safari/537.36"})
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return r.geturl(), r.read(400000).decode("utf-8", "ignore")


def to_text(html):
    html = re.sub(r"(?is)<(script|style|noscript|svg|header|footer|nav).*?</\1>", " ", html)
    txt = re.sub(r"(?s)<[^>]+>", " ", html)
    txt = re.sub(r"&[a-z#0-9]+;", " ", txt)
    return re.sub(r"\s+", " ", txt).strip()


def about_link(html, base):
    for m in re.finditer(r'href=["\']([^"\']+)["\']', html, re.I):
        h = m.group(1)
        if re.search(r"about|our-story|who-we-are|company|team", h, re.I) and not h.startswith(("mailto:", "tel:", "#")):
            return urllib.parse.urljoin(base, h)
    return None


def grab(lead):
    """Return (text, urls) for a Tier-2 candidate; ('', []) on failure."""
    try:
        url, html = fetch(lead["company_website"].strip())
        parts = [f"[HOME {url}]\n" + to_text(html)[:MAX_CHARS]]
        urls = [url]
        ab = about_link(html, url)
        if ab and ab.rstrip("/") != url.rstrip("/"):
            try:
                u2, h2 = fetch(ab)
                parts.append(f"\n\n[ABOUT {u2}]\n" + to_text(h2)[:MAX_CHARS]); urls.append(u2)
            except Exception:
                pass
        return "\n".join(parts), urls
    except Exception:
        return "", []


def main():
    import urllib.parse  # noqa
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=300); ap.add_argument("--niche", default="all")
    ap.add_argument("--only-clean", action="store_true")
    a = ap.parse_args()

    pre = {r["lead_id"]: r for r in csv.DictReader(PRE.open(encoding="utf-8-sig"))}
    ws = open_tab(SHEET_ID)
    hdr = ws.row_values(1); col = {h: i + 1 for i, h in enumerate(hdr)}
    rows = ws.get_all_records()

    # next N in send order with an empty status, spread across campaigns by send_order
    todo, skips = [], []
    for i, r in enumerate(rows):
        if a.niche != "all" and r["campaign"] != a.niche: continue
        if a.only_clean and r["mv_result"] != "ok": continue
        if str(r.get("personalization_status", "")).strip(): continue
        route = pre.get(r["lead_id"], {}).get("route", "TIER1_ONLY")
        (skips if route == "SKIP" else todo).append((i + 2, r, route))
    todo.sort(key=lambda t: (int(t[1]["send_order"]), t[1]["campaign"]))
    # round-robin by campaign so a day's batch mirrors the send mix
    by = {}
    for t in todo: by.setdefault(t[1]["campaign"], []).append(t)
    picked = []
    while len(picked) < a.n and any(by.values()):
        for c in list(by):
            if by[c] and len(picked) < a.n: picked.append(by[c].pop(0))

    bid = datetime.now().strftime("%Y%m%d_%H%M")
    bdir = BATCHES / bid; bdir.mkdir(parents=True, exist_ok=True)
    a1 = gspread.utils.rowcol_to_a1
    ups = []
    for rownum, r, _ in skips[:200]:
        ups.append({"range": a1(rownum, col["personalization_status"]), "values": [[f"skipped: off-niche ({pre[r['lead_id']]['niche_check']})"]]})
    for rownum, r, _ in picked:
        ups.append({"range": a1(rownum, col["personalization_status"]), "values": [["queued"]]})
    if ups: ws.batch_update(ups)

    t2 = [(rn, r) for rn, r, route in picked if route == "TIER2_CANDIDATE"]
    with ThreadPoolExecutor(16) as ex:
        texts = list(ex.map(lambda t: grab(t[1]), t2))
    got = 0
    leads = []
    for (rownum, r, route) in picked:
        rec = {k: r.get(k, "") for k in ("lead_id", "campaign", "first_name", "company_name", "company_website",
                                          "company_city", "company_state", "company_description", "headline", "industry", "company_size", "send_order", "mv_result")}
        rec["sheet_row"] = rownum; rec["route"] = route; rec["text_file"] = ""; rec["source_urls"] = []
        leads.append(rec)
    for (rownum, r), (txt, urls) in zip(t2, texts):
        rec = next(l for l in leads if l["lead_id"] == r["lead_id"])
        if txt:
            (bdir / f"{r['lead_id']}.txt").write_text(txt); rec["text_file"] = f"{r['lead_id']}.txt"; rec["source_urls"] = urls; got += 1
        else:
            rec["route"] = "TIER1_ONLY"
    (bdir / "leads.json").write_text(json.dumps(leads, indent=1))
    print(f"[pick] batch {bid}: {len(picked)} leads queued ({len(t2)} tier-2 candidates, {got} with page text), {len(skips)} off-niche skipped")
    print(f"[pick] by campaign: " + ", ".join(f"{c}={sum(1 for l in leads if l['campaign']==c)}" for c in ("recruiting","bookkeeping","cleaning")))
    print(f"[pick] dir: {bdir}")


if __name__ == "__main__":
    main()
