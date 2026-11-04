#!/usr/bin/env python3
"""Score Vollna RSS jobs for Lorenzo (read-only). Rubric: ~/advero/upwork/SCORING_RUBRIC_20261020.md
Usage: python3 score_vollna.py [--feeds /workspace/vollna_rss.txt] [--history CSV] [--hours 24] [--out selections.csv] [--top 12] [--min 55]
Fetches feeds with curl (GET only). Never posts, sends or changes anything.
Output is selection only: a selections list (job, link, score, reason). It never drafts proposals (Lorenzo rule 2026-10-20).
Budget is ignored completely. Client signals are used only if present in the feed item;
otherwise the score is re-weighted to keyword fit + tool depth + similarity to hired/replied jobs.
2026-10-21 10:55 CT: rubric exclusions are flags (the job is still scored); collect() is the importable fetch+score step;
the 0-100 RANK score (weights.json) used for the full list is in the RANK SCORE section. Scoring weights are unchanged."""
import argparse, csv, html, math, re, subprocess, sys, urllib.parse, collections
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo
CT = ZoneInfo("America/Chicago")

TOOLS = {  # tool -> regex (depth of software match)
 "n8n": r"\bn8n\b", "Make": r"\bmake\.com\b|\bmake \(integromat\)|\bintegromat\b|\bmake scenario", "Zapier": r"\bzapier\b",
 "GHL": r"\bgo ?high ?level\b|\bhighlevel\b|\bghl\b", "Claude": r"\bclaude\b|\banthropic\b", "OpenAI": r"\bopenai\b|\bchatgpt\b|\bgpt-?\d|\bllm",
 "AI agents": r"\bai agents?\b|\bagentic\b|\bai assistant|\bvoice agent|\bchatbot", "CRM": r"\bcrm\b|\bhubspot\b|\bsalesforce\b|\bpipedrive\b|\bclose\.com\b",
 "Cold email": r"\bcold email|\bcold outreach|\bsmartlead\b|\binstantly\b|\blemlist\b|\bdeliverability\b|\bemail sequence",
 "Clay/Apollo": r"\bclay\b|\bapollo\b", "Airtable": r"\bairtable\b", "Python/scraping": r"\bpython\b|\bweb scrap|\bapify\b",
 "Workspace tools": r"\bnotion\b|\bclickup\b|\bmonday\.com\b|\bgoogle sheets\b", "APIs/webhooks": r"\bapi\b|\bwebhooks?\b|\bintegrations?\b",
 "Retell/Vapi/Twilio": r"\bretell\b|\bvapi\b|\btwilio\b",
 "Deliverability infra": r"\bspf\b|\bdkim\b|\bdmarc\b|\bwarm-?up\b|\bgoogle workspace\b|\binbox rotation|\bmailbox",
}
TOOL_W = {"n8n":10,"Make":10,"GHL":10,"Claude":9,"AI agents":9,"Cold email":9,"Zapier":8,"OpenAI":7,"CRM":7,"Clay/Apollo":6,
          "Airtable":6,"Python/scraping":4,"Workspace tools":4,"APIs/webhooks":3,"Retell/Vapi/Twilio":6,"Deliverability infra":8}
FIT_TERMS = {  # lane keywords (keyword fit)
 r"\bautomat": 8, r"\bworkflow": 6, r"\bai automation": 8, r"\blead gen": 6, r"\boutbound\b": 7, r"\bpipeline": 4,
 r"\bfollow[- ]?up": 5, r"\blead routing|\brouting\b": 5, r"\bintake\b": 4, r"\bbooking|\bappointment": 4, r"\breactivat": 6,
 r"\bsequence": 4, r"\bintegrat": 4, r"\bsystem": 3, r"\bcrm\b": 5, r"\bdashboard": 3, r"\bai\b": 3, r"\bagent": 4,
 r"\bsetup|\bset up": 3, r"\bb2b\b": 3, r"\blocal business|\bhome service|\bcontractor|\broof": 5,
}
EXCLUDE = [  # (label, regex on title + categories, regex that rescues it if strongly automation)
 ("design", r"\b(logo|graphic design|ui/ux|figma|web design(er)?|brand(ing)? design|illustrat|canva|landing page design)\b"),
 ("video", r"\b(video edit|videograph|video production|youtube editor|ugc|motion graphic|animation)\b"),
 ("VA", r"\b(virtual assistant|executive assistant|personal assistant|\bva\b)"),
 ("data entry", r"\bdata entry\b"),
 ("SEO", r"\bseo\b|search engine optimi"),
 ("ads-only", r"\b(google ads|ppc|meta ads|facebook ads|media buyer|paid ads|tiktok ads|ads manager|ad campaign)\b"),
 ("full-time W2", r"\bw-?2\b|full[- ]time (employee|position|role)|\bon-?site\b|in[- ]office"),
 ("commission-only", r"commission[- ]only|commission[- ]based|100% commission|paid on commission"),
 ("SDR/appointment setter", r"\b(sdr|bdr|appointment setter|cold call(er|ing)|telemarket|sales rep(resentative)?)\b"),
 ("writing/translation", r"\b(translat|manuscript|ghostwrit|copywriter for blog|article writ|transcription|proofread)\b"),
 ("social media mgmt", r"\bsocial media (manager|management|marketer)\b"),
 ("pure software engineering", r"\b(full[- ]?stack|senior .*engineer|node/react|mongodb|trading bot|telegram developer|app developer|visualization app)\b"),
 ("industry SME role", r"\bsubject matter expert\b"),
 ("sales/phone role", r"\b(sales ?person|sales professional|phone expert|acquisitions)\b"),
]
TEXT_EXCLUDE = [  # hard disqualifiers found anywhere in the post
 ("full-time W2", r"job type:\s*full[- ]time|full[- ]time hire|direct job to full|\bw-?2\b"),
 ("commission-only", r"commission[- ]only|100% commission|pay per approved|paid only on|milestone-based sign-ups"),
 ("sales rep role", r"motivated sales ?person|sell .{0,40}to businesses.{0,40}close deals"),
]
MANUAL = r"cold call|telemarket|you will be provided with a list|scripts to use|phone communication|reach out to \d+ businesses per day|follow up by phone"
EXCLUDE_CATS = r"(Design & Creative|Translation|Writing|Video|Admin Support|Customer Service)"
STOP = set("the a an and or for to of in on with we you our is are be need looking help this that it i my your who will from as at by can have has not but all any us".split())

def toks(s): return [w for w in re.findall(r"[a-z0-9\.]+", s.lower()) if w not in STOP and len(w) > 2]

def job_id(url):
    m = re.search(r"~0?([0-9]{15,})", urllib.parse.unquote(urllib.parse.unquote(url or ""))); return m.group(1) if m else ""
def norm_title(t): return re.sub(r"[^a-z0-9]+", " ", re.sub(r"\((fixed price|hourly)[^)]*\)\s*$", "", t, flags=re.I).lower()).strip()

def load_history(path):
    rows = list(csv.DictReader(open(path, encoding="utf-8"), delimiter=";"))
    pos = [r for r in rows if r["Status"] in ("Hired", "Replied")]
    ids = {job_id(r["Job URL"]) for r in rows} - {""}; titles = {norm_title(r["Job Title"]) for r in rows}
    df = collections.Counter(); docs = []
    for r in rows:
        d = collections.Counter(toks(r["Job Title"] + " " + r["Job Skills"] + " " + r["Job Description"][:1500])); docs.append((r, d)); df.update(set(d))
    N = len(rows); idf = {w: math.log((N + 1) / (c + 1)) + 1 for w, c in df.items()}
    def vec(c): return {w: (1 + math.log(n)) * idf.get(w, math.log(N + 1) + 1) for w, n in c.items()}
    posv = [(r, vec(d)) for r, d in docs if r["Status"] in ("Hired", "Replied")]
    return rows, pos, ids, titles, posv, vec

def cos(a, b):
    num = sum(v * b.get(k, 0) for k, v in a.items()); den = math.sqrt(sum(v*v for v in a.values())) * math.sqrt(sum(v*v for v in b.values()))
    return num / den if den else 0

def parse_feed(name, url):
    xml = subprocess.run(["curl", "-sL", "-m", "40", url], capture_output=True, text=True).stdout
    out = []
    try: root = ET.fromstring(xml)
    except ET.ParseError: return out
    for it in root.iter("item"):
        title = html.unescape(it.findtext("title") or ""); desc = html.unescape(it.findtext("description") or "")
        link = it.findtext("link") or ""; pub = parsedate_to_datetime(it.findtext("pubDate"))
        cats = [c.text or "" for c in it.iter("category")]
        up = urllib.parse.unquote(urllib.parse.unquote(urllib.parse.parse_qs(urllib.parse.urlparse(link).query).get("url", [link])[0]))
        bt = "hourly" if re.search(r"\(Hourly", title) else "fixed" if re.search(r"\(Fixed Price", title) else "unknown"
        out.append(dict(feed=name, btype=bt, title=re.sub(r"\s*\((Fixed Price|Hourly)[^)]*\)\s*$", "", title).strip(), desc=desc, link=up, vollna_link=link, pub=pub, cats=cats))
    return out

def client_signals(desc):
    """Only if Vollna includes client stats in the item text. Returns (points 0-25, stats str) or (None, 'not in feed')."""
    g = lambda p: (re.search(p, desc, re.I) or [None, None])[1]
    spent = g(r"(?:total )?spent:?\s*\$?(\d[\d,.]*[kKmM]?)"); hires = g(r"(?:hires|jobs posted|total hires):?\s*(\d+)"); reviews = g(r"reviews:?\s*(\d+)")
    pv = re.search(r"payment (method )?verified", desc, re.I)
    if not any([spent, hires, reviews, pv]): return None, "not in feed"
    def money(s):
        s = s.replace(",", "").lower(); m = 1000 if s.endswith("k") else 1e6 if s.endswith("m") else 1
        return float(s.rstrip("km")) * m
    p = 0; parts = []
    if spent: v = money(spent); p += 10 if v > 1000 else 4 if v > 0 else 0; parts.append(f"spent ${spent}")
    if hires: p += min(7, int(hires)); parts.append(f"hires {hires}")
    if reviews: p += min(5, int(reviews)); parts.append(f"reviews {reviews}")
    if pv: p += 3; parts.append("payment verified")
    return min(25, p), "; ".join(parts)

def history_fit(job, text, spent_val=None, country=None):
    """Patterns from deep_patterns_148_20261020.md (8 wins / 148). Shown as its own line. Budget AMOUNT is never used;
    only the hourly/fixed contract type, and nothing is disqualified on it."""
    pts, why = 0, []
    if job["btype"] == "hourly": pts += 4; why.append("hourly +4 (7/56 vs fixed 1/75)")
    elif job["btype"] == "fixed": pts -= 3; why.append("fixed -3")
    body = re.split(r"\n\s*Skills:", job["desc"])[0]; wc = len(body.split())
    if wc < 120: pts += 5; why.append(f"{wc}w desc +5 (<120w 7/63)")
    elif wc >= 200: pts -= 5; why.append(f"{wc}w desc -5 (200w+ 0/57)")
    else: why.append(f"{wc}w desc 0")
    if country: 
        if re.search(r"united states|\busa?\b", country, re.I): pts += 3; why.append("US client +3")
        else: why.append("non-US client 0")
    else: why.append("country n/a in feed")
    if spent_val is not None and 10000 <= spent_val <= 50000: pts += 3; why.append("spent $10k-50k +3")
    if re.search(r"\bworkflows?\b", text): pts -= 3; why.append("'workflow' -3 (1/102)")
    tech = re.findall(r"\b(api|apis|webhooks?|python|json|sdk|javascript)\b", text)
    if tech: pts -= 3; why.append(f"tech terms ({', '.join(sorted(set(tech)))}) -3")
    posk = [k for k, rx in {"lead gen": r"\blead gen", "cold email": r"\bcold email", "Claude": r"\bclaude\b", "Make": r"\bmake\.com\b|\bmake scenario"}.items() if re.search(rx, text)]
    if posk: b = min(6, 2 * len(posk)); pts += b; why.append(f"{'/'.join(posk)} +{b}")
    if re.search(r"\bai agents?\b", text): pts -= 3; why.append("'AI agent' -3 (0/14)")
    return pts, "; ".join(why)

def score(job, posv, vec):
    text = (job["title"] + " " + job["desc"]).lower(); head = (job["title"] + " " + " ".join(job["cats"])).lower()
    tools = [t for t, rx in TOOLS.items() if re.search(rx, text, re.I)]
    title_tools = [t for t, rx in TOOLS.items() if re.search(rx, job["title"], re.I)]
    # Rubric exclusions are a FLAG, not a drop (Lorenzo 2026-10-21 10:52 CT: full list, he picks).
    # The label is returned in "excluded"; the job is still scored with the same weights below.
    excl = ""
    for lab, rx in EXCLUDE:
        if re.search(rx, job["title"], re.I) and not (title_tools and lab in ("design", "data entry", "SEO", "ads-only", "social media mgmt")):
            excl = lab; break
    if not excl and re.search(EXCLUDE_CATS, " ".join(job["cats"])) and sum(TOOL_W[t] for t in tools if t != "APIs/webhooks") < 14:
        excl = "out-of-lane category: " + "/".join(job["cats"])
    if not excl:
        for lab, rx in TEXT_EXCLUDE:
            if re.search(rx, text, re.I): excl = lab; break
    if not excl and re.search(r"facebook ad|instagram ad|meta ads? specialist", text, re.I) and not re.search(r"automat|workflow|n8n|zapier|make\.com", job["title"], re.I):
        excl = "ads-only"
    tool_raw = sum(TOOL_W[t] for t in tools) + 4 * len(title_tools)
    kw_raw = sum(w for rx, w in FIT_TERMS.items() if re.search(rx, text, re.I)) + sum(4 for rx in FIT_TERMS if re.search(rx, job["title"], re.I))
    v = vec(collections.Counter(toks(job["title"] + " " + job["desc"][:1500])))
    sims = sorted(((cos(v, pv), r["Job Title"]) for r, pv in posv), reverse=True)
    best_sim, best_title = sims[0]
    cs, stats = client_signals(job["desc"])
    if cs is None:  # thin/unknown client: re-weight, no penalty
        W = dict(client=0, kw=40, tool=40, sim=20)
    else:
        W = dict(client=25, kw=30, tool=30, sim=15)
    kw = W["kw"] * min(1, kw_raw / 45); tl = W["tool"] * min(1, tool_raw / 30); sm = W["sim"] * min(1, best_sim / 0.30)
    manual = -10 if re.search(MANUAL, text, re.I) else 0  # manual-execution outreach (DMs/calls from scripts) is not a systems job
    hf, hf_why = history_fit(job, text)
    total = max(0, min(100, round((cs or 0) + kw + tl + sm + manual + hf)))
    return dict(excluded=excl, tools=tools, client_pts=cs, client_stats=stats, kw=round(kw, 1), tool=round(tl, 1), sim=round(sm, 1),
                sim_to=best_title, sim_raw=round(best_sim, 3), manual=manual, hist=hf, hist_why=hf_why, total=total, weights=W,
                kw_raw=kw_raw, tool_raw=tool_raw)

# Judgment overrides after reading the full post (job-id -> reason). Kept in code so reruns are reproducible.
SKIP = {"22112517523622977561": "mostly ops/admin execution (compliance packets, credential tracking, closeout docs), outreach is 35%"}

def write_selections(path, res, top, minimum):
    sel = [(j, s) for j, s in res if not s["excluded"] and s["total"] >= minimum and job_id(j["link"]) not in SKIP][:top]
    with open(path, "w", newline="") as f:
        w = csv.writer(f); w.writerow(["job_title","url","feed","posted_ct","contract_type","client_stats","score_breakdown","history_fit","total","reason"])
        for j, s in sel:
            W = s["weights"]
            bd = (f"client {s['client_pts'] if s['client_pts'] is not None else 'n/a (re-weighted)'}/{W['client']}; keyword fit {s['kw']}/{W['kw']}; "
                  f"tool depth {s['tool']}/{W['tool']}; similarity bonus {s['sim']}/{W['sim']} (closest win: {s['sim_to']})" + (f"; manual-execution penalty {s['manual']}" if s['manual'] else ""))
            w.writerow([j["title"], j["link"], j["feed"], j["pub"].astimezone(CT).strftime("%Y-%m-%d %H:%M CT"), j["btype"], s["client_stats"], bd,
                        f"{s['hist']:+d} ({s['hist_why']})", s["total"],
                        "tools: " + ", ".join(t for t in s["tools"] if t != "APIs/webhooks")])
    return sel

# ---------------------------------------------------------------------------------------------
# RANK SCORE (Lorenzo 2026-10-21 10:54 CT). 0-100, used to order the full list. No cutoff, no auto-pick.
# Weights live in ~/advero/upwork/weights.json (versioned; history in weights_history.jsonl).
# Each signal gives a normalized sub-score 0..1; points = weight * sub. Missing client signal = 0.5 (n/a).
# The rubric "total" above is unchanged and is still what picks_log.csv records as "score".
# ---------------------------------------------------------------------------------------------
import json, os
WEIGHTS_FILE = os.path.expanduser("~/advero/upwork/weights.json")
SIGNALS = ["tools", "category", "feedback", "spend", "age", "interviews"]
V1_WEIGHTS = {"tools": 30, "category": 20, "feedback": 15, "spend": 15, "age": 10, "interviews": 10}
LANE_CORE = {"Sales & Marketing", "Lead Generation & Telemarketing", "Digital Marketing", "AI & Machine Learning", "AI Apps & Integration",
             "Scripts & Utilities", "Data Mining & Management", "Marketing, PR & Brand Strategy", "Marketing Automation"}
LANE_ADJ = {"Web, Mobile & Software Dev", "Web Development", "Data Science & Analytics", "Ecommerce Development", "IT & Networking",
            "DevOps & Solution Architecture", "Management Consulting & Analysis", "Accounting & Consulting", "Network & System Administration",
            "Data Analysis & Testing", "QA & Testing"}
OFFTOPIC_CAP = 0.15  # category sub-score cap for rubric-excluded / SKIP jobs (flagged, never dropped)

def load_weights(path=WEIGHTS_FILE):
    """-> (version, weights dict). Falls back to v1 if the file is missing/broken (and says so in version)."""
    try:
        d = json.load(open(path)); w = {k: float(d["weights"][k]) for k in SIGNALS}; return d["version"], w
    except Exception:
        return "v1-fallback", dict(V1_WEIGHTS)

def lane_value(cats):
    if not cats: return 0.5
    vals = [1.0 if c in LANE_CORE else 0.6 if c in LANE_ADJ else 0.2 for c in cats]
    return max(vals)

def static_subs(job, s):
    """Signals fixed at first sight: tools (tool depth) and category (lane of Vollna categories + keyword fit)."""
    tools_sub = min(1.0, (s.get("tool_raw") or 0) / 30)
    kw_sub = min(1.0, (s.get("kw_raw") or 0) / 45)
    cat_sub = 0.5 * lane_value(job.get("cats") or []) + 0.5 * kw_sub
    flags = []
    if s.get("excluded"): flags.append(f"off-topic {s['excluded']}")
    if job_id(job.get("link", "")) in SKIP: flags.append(f"SKIP: {SKIP[job_id(job['link'])]}")
    if flags: cat_sub = min(cat_sub, OFFTOPIC_CAP)
    return round(tools_sub, 4), round(cat_sub, 4), flags

def _num(x):
    if x is None: return None
    if isinstance(x, (int, float)): return float(x)
    t = str(x).strip().lower().replace(",", "").replace("$", "").replace("%", "")
    if t in ("", "n/a", "na", "none", "unknown", "-"): return None
    mult = 1000 if t.endswith("k") else 1e6 if t.endswith("m") else 1
    try: return float(t.rstrip("km")) * mult
    except ValueError: return None

def client_subs(client):
    """client: dict from Vollna text or client_cache.json (spend, feedback, interviewing). None/blank = n/a = 0.5."""
    client = client or {}
    fb = _num(client.get("feedback")); sp = _num(client.get("spend")); iv = _num(client.get("interviewing"))
    fb_sub = 0.5 if fb is None else max(0.2, min(1.0, (fb - 3.0) / 2.0))          # 5.0 -> 1, <=3.4 -> 0.2 floor
    sp_sub = 0.5 if sp is None else max(0.3, min(1.0, math.log10(sp + 1) / 5))      # $0 -> 0.3 floor (thin client), $100k -> 1
    iv_sub = 0.5 if iv is None else max(0.0, 1 - iv / 20)                           # 0 -> 1, 20+ -> 0
    return {"feedback": (round(fb_sub, 4), fb is None), "spend": (round(sp_sub, 4), sp is None), "interviews": (round(iv_sub, 4), iv is None)}

def age_sub(age_h):
    return 1.0 if age_h <= 1 else max(0.0, 1 - (age_h - 1) / 23)                    # <1h full, 24h -> 0

def rank_score(subs, weights):
    """subs: signal -> 0..1. Returns (total 0-100, points per signal)."""
    pts = {k: round(weights[k] * subs[k], 2) for k in SIGNALS}
    return round(sum(pts.values()), 1), pts


def collect(feeds, history, hours):
    """Fetch the Vollna feeds (GET only), dedupe, mark already-applied, score. Returns (res, per_feed, window)."""
    rows, pos, ids, titles, posv, vec = load_history(history)
    now = datetime.now(timezone.utc); seen = {}; per_feed = collections.Counter(); window = {}
    for line in open(feeds):
        if "\t" not in line: continue
        name, url = line.rstrip("\n").split("\t", 1); items = parse_feed(name, url); per_feed[name] = len(items)
        if items: window[name] = (min(i["pub"] for i in items), max(i["pub"] for i in items))
        for j in items:
            if now - j["pub"] > timedelta(hours=hours): continue
            k = job_id(j["link"]) or norm_title(j["title"])
            dup = next((x for x in seen.values() if norm_title(x["title"]) == norm_title(j["title"])), None)
            if k in seen or dup:
                d = seen.get(k) or dup
                if name not in d["feed"]: d["feed"] += " + " + name
                d.setdefault("dupes", []).append(j["link"]); continue
            seen[k] = j
    res = []
    for k, j in seen.items():
        if job_id(j["link"]) in ids or norm_title(j["title"]) in titles: s = dict(excluded="already applied")
        else: s = score(j, posv, vec)
        res.append((j, s))
    res.sort(key=lambda x: -(x[1].get("total") or -1))
    return res, per_feed, window

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--feeds", default="/workspace/vollna_rss.txt"); ap.add_argument("--history", default="/home/box/Downloads/proposals_2026_10_20_20_16_16.csv")
    ap.add_argument("--hours", type=float, default=24); ap.add_argument("--out", default="/home/box/advero/upwork/scored_all_latest.csv")
    ap.add_argument("--top", type=int, default=12); ap.add_argument("--min", type=int, default=55)
    ap.add_argument("--selections", default="", help="write selections CSV here")
    a = ap.parse_args()
    res, per_feed, window = collect(a.feeds, a.history, a.hours)
    with open(a.out, "w", newline="") as f:
        w = csv.writer(f); w.writerow(["title","url","feed","posted_ct","excluded","client_stats","client_pts","keyword_fit","tool_depth","similarity_bonus","history_fit","history_fit_detail","total","tools","closest_past_win"])
        for j, s in res:
            w.writerow([j["title"], j["link"], j["feed"], j["pub"].astimezone(CT).strftime("%Y-%m-%d %H:%M CT"), s.get("excluded",""), s.get("client_stats",""),
                        s.get("client_pts",""), s.get("kw",""), s.get("tool",""), s.get("sim",""), s.get("hist",""), s.get("hist_why",""), s.get("total",""), ", ".join(s.get("tools",[])), s.get("sim_to","")])
    if a.selections:
        sel = write_selections(a.selections, res, a.top, a.min); print(f"SELECTED {len(sel)} -> {a.selections}")
    for n, c in per_feed.items():
        lo, hi = window.get(n, (None, None))
        print(f"FEED {n}: {c} items" + (f", window {lo.astimezone(CT):%m-%d %H:%M} to {hi.astimezone(CT):%H:%M} CT" if lo else ""))
    print(f"unique in last {a.hours}h: {len(res)}; excluded: {sum(1 for _, s in res if s['excluded'])}")
    for j, s in res:
        print(s.get("total", "--"), f"(hf {s.get('hist','')})", "|", s.get("excluded", ""), "|", j["feed"][:12], "|", j["title"][:90], "|", ",".join(s.get("tools", [])), "|", s.get("sim_to", "")[:40])

if __name__ == "__main__": main()
