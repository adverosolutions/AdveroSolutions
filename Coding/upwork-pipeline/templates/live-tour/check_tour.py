#!/usr/bin/env python3
"""Live tour checker (templates/live-tour, DIRECTIVES U-020).

Usage:
  /usr/bin/python3 check_tour.py <job tour folder> [--page FILE] [--proposal FILE]
                                 [--product NAME] [--allow PHRASE ...] [--require-verify]

Defaults: --page tour.html (falls back to index.html), --proposal proposal.md.
Checks the page and the proposal against the honesty and copy rules in
templates/live-tour/README.md, prints a PASS/FAIL list and a JSON summary.
Exit code 0 only when every check passes (WARN does not fail the run).
Stdlib only. Read-only: it never edits the folder.
"""
import argparse
import json
import os
import re
import sys
from html.parser import HTMLParser

EM = "\u2014"
EN = "\u2013"
LOOM_MARK = "https://www.loom"
RUNTIME_PLACEHOLDER = "[N]"
PREVIEW_MIN, PREVIEW_MAX = 133, 150

# Price and billing words (U-020 list). Case-insensitive, whole words.
PRICE_PATTERNS = [
    (r"\$\s?\d[\d,.]*\s*[kKmM]?\+?", "$ amount"),
    (r"\bper\s+hour\b", "per hour"),
    (r"\bhourly\b", "hourly"),
    (r"\brates?\b", "rate"),
    (r"\bbudget\b", "budget"),
    (r"\binvoice\s+me\b", "invoice me"),
    (r"\bfixed[\s-]+price\b", "fixed price"),
    (r"\bretainer\b", "retainer"),
]
# "rate" as a metric name is not billing talk.
METRIC_RATE = re.compile(
    r"\b(reply|response|conversion|open|click|close|win|error|success|bounce|churn|booking|"
    r"show|match|approval|agreement|completion|delivery|resolution|acceptance|hit)[\s-]+rates?\b",
    re.I)

# Text from the HubSpot EXAMPLE panels in tour.html. Must be gone when the job is not HubSpot.
HUBSPOT_EXAMPLE = ["HubSpot", "Priya Shah", "Northgate Logistics", "Jordan Lee", "Marcus Bell",
                   "Ridgeway Supply", "Ana Ortiz", "Coastline Studio", "Dev Patel", "Harbor Tools",
                   "Task 8042", "51864", "quotes routed faster"]

# Named products that need the "not a <product> screen" title bar if they appear.
KNOWN_PRODUCTS = ["HubSpot", "Salesforce", "GoHighLevel", "HighLevel", "GHL", "QuickBooks", "Xero",
                  "Excel", "Google Sheets", "Gmail", "Outlook", "Airtable", "Notion", "Shopify",
                  "Zoho", "Pipedrive", "Monday.com", "ClickUp", "Zendesk", "Intercom", "Clay",
                  "Apollo", "Instantly", "Slack", "Stripe", "Calendly", "Asana", "Trello",
                  "Follow Up Boss", "kvCORE", "Close CRM", "Attio", "Freshdesk", "Jira"]

OUTCOME_HONESTY = re.compile(r"baseline not measured yet|not measured yet|goals,? not results", re.I)


class Visible(HTMLParser):
    """Collects visible text (text nodes outside script/style, plus aria-label/title/alt/
    placeholder attributes and <title>) and the JS string literals inside <script>."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.text = []          # (text, in_goals)
        self.scripts = []
        self.proto = []
        self.goal_depth = None
        self.has_outcomes_markup = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = (a.get("class") or "").split()
        if tag not in ("br", "img", "input", "meta", "link", "hr"):
            self.stack.append((tag, cls, a.get("id")))
        if a.get("id") == "goals" and self.goal_depth is None:
            self.goal_depth = len(self.stack)
        if "vo" in cls or "mc" in cls or a.get("id") == "metrics":
            self.has_outcomes_markup = True
        for k in ("aria-label", "title", "alt", "placeholder"):
            if a.get(k):
                self.text.append((a[k], self._in_goals()))

    def handle_startendtag(self, tag, attrs):
        a = dict(attrs)
        for k in ("aria-label", "title", "alt", "placeholder"):
            if a.get(k):
                self.text.append((a[k], self._in_goals()))

    def handle_endtag(self, tag):
        if not any(t == tag for t, _, _ in self.stack):
            return  # stray close tag
        while self.stack:
            t, _, _ = self.stack.pop()
            if self.goal_depth is not None and len(self.stack) < self.goal_depth:
                self.goal_depth = None
            if t == tag:
                break

    def _in(self, tag):
        return any(t == tag for t, _, _ in self.stack)

    def _in_goals(self):
        return self.goal_depth is not None and len(self.stack) >= self.goal_depth

    def handle_data(self, data):
        if self._in("style"):
            return
        if self._in("script"):
            self.scripts.append(data)
            return
        if any("proto" in c for _, c, _ in self.stack):
            self.proto.append(data)
        if data.strip():
            self.text.append((data, self._in_goals()))


def js_strings(src):
    """String literals from JS source (single, double and backtick quoted)."""
    out = []
    for m in re.finditer(r'"((?:[^"\\\n]|\\.)*)"|\'((?:[^\'\\\n]|\\.)*)\'|`((?:[^`\\]|\\.)*)`', src):
        s = next(g for g in m.groups() if g is not None)
        if s.strip():
            out.append(s)
    return out


def script_steps(src):
    """The var S=[...] step objects, each as raw text, in order."""
    m = re.search(r"var\s+S\s*=\s*\[(.*?)\n\s*\];", src, re.S)
    if not m:
        return []
    body = m.group(1)
    return [b for b in re.split(r"\n\s*\{k:", body) if b.strip()]


def dash_hits(text):
    hits = []
    for m in re.finditer(EM, text):
        hits.append(snip(text, m.start()))
    for m in re.finditer(EN, text):
        before = text[m.start() - 1] if m.start() > 0 else ""
        after = text[m.end()] if m.end() < len(text) else ""
        if before.isdigit() and after.isdigit():
            continue  # number range like 9–12, not used as a dash
        hits.append(snip(text, m.start()))
    return hits


def snip(text, i, w=40):
    return re.sub(r"\s+", " ", text[max(0, i - w): i + w]).strip()


def price_hits(text, allow):
    hits = []
    low_allow = [a.lower() for a in allow]
    for pat, name in PRICE_PATTERNS:
        for m in re.finditer(pat, text, re.I):
            ctx = snip(text, m.start(), 60)
            if name == "rate":
                around = text[max(0, m.start() - 30): m.end()]
                if METRIC_RATE.search(around):
                    continue
            if any(a in ctx.lower() for a in low_allow):
                continue
            hits.append("{}: ...{}...".format(name, ctx))
    return hits


def preview_of(text):
    body = text.lstrip()
    i = body.find(LOOM_MARK)
    return None if i < 0 else body[: i + len(LOOM_MARK)]


def count_preview(p):
    return len(p) - (len(RUNTIME_PLACEHOLDER) - 1) * p.count(RUNTIME_PLACEHOLDER)


def split_proposal(md):
    """(proposal body, notes). Notes start at the '---' rule or 'Notes for Lorenzo'."""
    m = re.search(r"^\s*---\s*$|^#+\s*Notes for Lorenzo", md, re.M)
    return (md[: m.start()], md[m.start():]) if m else (md, "")


def find_report(folder):
    found = []
    for root, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if d not in ("node_modules", "_backup")]
        if "report.json" in files:
            p = os.path.join(root, "report.json")
            found.append((os.path.getmtime(p), p))
    return max(found)[1] if found else None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder")
    ap.add_argument("--page", help="page file in the folder (default tour.html, else index.html)")
    ap.add_argument("--proposal", default="proposal.md")
    ap.add_argument("--product", help="the client's named product, if the title bar can't tell")
    ap.add_argument("--allow", action="append", default=[],
                    help="phrase from the client's own post to skip in the price check (repeatable)")
    ap.add_argument("--require-verify", action="store_true", help="fail when no verify report.json exists")
    args = ap.parse_args()

    folder = os.path.abspath(args.folder)
    results = []

    def add(name, ok, detail="", level=None):
        results.append({"check": name, "status": level or ("PASS" if ok else "FAIL"), "detail": detail})

    page_name = args.page or ("tour.html" if os.path.exists(os.path.join(folder, "tour.html")) else "index.html")
    page_path = os.path.join(folder, page_name)
    prop_path = os.path.join(folder, args.proposal)
    if not os.path.isfile(page_path) or not os.path.isfile(prop_path):
        add("files present", False, "missing: " + ", ".join(p for p in (page_path, prop_path) if not os.path.isfile(p)))
        return finish(folder, page_name, args.proposal, results)
    add("files present", True, "{} and {}".format(page_name, args.proposal))

    html = open(page_path, encoding="utf-8").read()
    md = open(prop_path, encoding="utf-8").read()
    html_nc = re.sub(r"<!--.*?-->", "", html, flags=re.S)  # comments are builder notes, not copy

    v = Visible()
    v.feed(html_nc)
    script_src = "\n".join(v.scripts)
    strings = js_strings(script_src)
    vis_all = [t for t, _ in v.text] + strings
    vis_text = "\n".join(vis_all)
    vis_not_goals = "\n".join([t for t, g in v.text if not g] + strings)
    body, notes = split_proposal(md)
    # P.S. bullets are approved case-study results, word for word; their $ figures are not price talk.
    body_no_ps = re.sub(r"^\s*->.*$", "", body, flags=re.M)

    # 1. dashes
    h = dash_hits(vis_text)
    add("no em/en dash in page copy", not h, "; ".join(h[:5]) or "none")
    h = dash_hits(md)
    add("no em/en dash in proposal", not h, "; ".join(h[:5]) or "none")

    # 2. prototype badge
    ok = re.search(r"Illustrative prototype", " ".join(t for t, _ in v.text)) is not None and \
        re.search(r'class="badge"[^>]*>.*?Illustrative prototype', html_nc, re.S) is not None
    add("'Illustrative prototype' badge", ok, "found in .badge" if ok else "no .badge with 'Illustrative prototype'")

    # 3. title bar when a named product appears
    proto = re.sub(r"\s+", " ", " ".join(v.proto)).strip()
    m = re.search(r"not an? (.+?) screen", proto)
    product = (m.group(1).strip() if m else None) or args.product
    named = [p for p in KNOWN_PRODUCTS if re.search(r"\b" + re.escape(p) + r"\b", vis_text)]
    if m and "{{" not in m.group(1):
        add("'not a <product> screen' title bar", True, proto)
    elif named:
        add("'not a <product> screen' title bar", False,
            "named product(s) shown ({}) but title bar is '{}'".format(", ".join(named), proto or "missing"))
    else:
        add("'not a <product> screen' title bar", True, "no named product on the page", "PASS")

    # 4. outcomes shown -> goals-not-results wording
    outcomes = v.has_outcomes_markup or re.search(r"\boutcomes?\b", vis_text, re.I) is not None
    if outcomes:
        ok = OUTCOME_HONESTY.search(vis_text) is not None
        add("goals-not-results wording", ok,
            "'Baseline not measured yet' or 'goals, not results' found" if ok else "outcomes shown without it")
    else:
        add("goals-not-results wording", True, "no outcomes shown")

    # 5. price and billing words
    h = price_hits(vis_not_goals, args.allow)
    add("no price/billing words in page", not h, "; ".join(h[:6]) or "none (goal quotes from the post skipped)")
    h = price_hits(body_no_ps, args.allow)
    add("no price/billing words in proposal", not h, "; ".join(h[:6]) or "none (P.S. case-study bullets skipped)")

    # 6. leftover placeholders and HubSpot example text
    ph = sorted(set(re.findall(r"\{\{[^}]*\}\}", html_nc)))
    add("no leftover {{PLACEHOLDERS}}", not ph, ", ".join(ph[:10]) or "none")
    jd = ""
    jd_path = os.path.join(os.path.dirname(folder), "jd.txt")
    if os.path.isfile(jd_path):
        jd = open(jd_path, encoding="utf-8", errors="replace").read()
    is_hubspot = bool((product and "hubspot" in product.lower()) or "hubspot" in jd.lower())
    if is_hubspot:
        add("no HubSpot example text (non-HubSpot job)", True, "HubSpot job, skipped")
    else:
        left = [s for s in HUBSPOT_EXAMPLE if s.lower() in vis_text.lower()]
        add("no HubSpot example text (non-HubSpot job)", not left, ", ".join(left) or "none")

    # 7. proposal preview length
    pv = preview_of(md)
    if pv is None:
        add("preview 133 to 150 chars", False, "no '{}' in proposal".format(LOOM_MARK))
    else:
        n = count_preview(pv)
        add("preview 133 to 150 chars", PREVIEW_MIN <= n <= PREVIEW_MAX, "{} chars ([N] counts as 1)".format(n))

    # 8. Loom placeholder
    if "https://www.loom.com/share/[LOOMURL]" in body:
        add("Loom placeholder", True, "https://www.loom.com/share/[LOOMURL]")
    elif re.search(r"https://www\.loom\.com/share/[A-Za-z0-9]{8,}", body):
        add("Loom placeholder", True, "real Loom URL already filled in (finalized)")
    else:
        add("Loom placeholder", False, "no https://www.loom.com/share/[LOOMURL]")

    # 8b. locked walkthrough line (UPWORK_PROCESS.md section 6). Counted over the whole file,
    # notes included, the same way verify_job.check_proposal counts it.
    walks = len(re.findall(r"the video walks through", md, re.I))
    add("'The video walks through' exactly once", walks == 1,
        "found {}x in {} (needs exactly 1, notes included)".format(walks, args.proposal))

    # 9. ends with the 15-minute call question
    paras = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    sig = next((i for i, p in enumerate(paras) if p == "Lorenzo" or p.startswith("Lorenzo\n")), None)
    last = paras[sig - 1] if sig else (paras[-1] if paras else "")
    call = re.compile(r"15[\s-]minute call", re.I)
    ok = bool(call.search(last) and "?" in last)
    add("proposal ends with 15-minute call question", ok, "..." + re.sub(r"\s+", " ", last)[-90:] if last else "empty")
    steps = script_steps(script_src)
    ok = bool(steps and call.search(steps[-1]))
    add("tour ends on the 15-minute call", ok,
        "last of {} steps mentions it".format(len(steps)) if ok else "last step ({} steps) has no 15-minute call".format(len(steps)))

    # 10. verify report
    rp = find_report(folder)
    if not rp:
        add("verify report.json all passing", not args.require_verify,
            "no report.json yet (run verify.mjs)", None if args.require_verify else "WARN")
    else:
        problems = []
        try:
            rep = json.load(open(rp, encoding="utf-8"))
        except Exception as e:
            rep, problems = {}, ["unreadable: {}".format(e)]
        for mode in ("desktop", "mobile", "reduced"):
            steps_r = rep.get(mode)
            if not steps_r:
                problems.append("{}: missing".format(mode))
                continue
            for i, s in enumerate(steps_r, 1):
                if s.get("bad"):
                    problems.append("{} step {} bad {}".format(mode, i, s["bad"][:2]))
                if s.get("docOverflow"):
                    problems.append("{} step {} docOverflow".format(mode, i))
                if s.get("running"):
                    problems.append("{} step {} running {}".format(mode, i, s["running"]))
                if s.get("font") is False:
                    problems.append("{} step {} font not loaded".format(mode, i))
        if (rep.get("backToStart") or {}).get("hash") != "#1":
            problems.append("backToStart hash {}".format((rep.get("backToStart") or {}).get("hash")))
        if rep.get("errors"):
            problems.append("errors {}".format(rep["errors"][:3]))
        nd = len(rep.get("desktop") or [])
        if steps and nd and nd != len(steps):
            problems.append("report has {} steps, page has {}".format(nd, len(steps)))
        if os.path.getmtime(rp) < os.path.getmtime(page_path):
            problems.append("report is older than {} (run verify.mjs again)".format(page_name))
        add("verify report.json all passing", not problems,
            "; ".join(problems[:6]) or "{} ({} steps x 3 modes, back to #1, no errors)".format(
                os.path.relpath(rp, folder), rep.get("steps") or nd))

    return finish(folder, page_name, args.proposal, results)


def finish(folder, page, proposal, results):
    for r in results:
        print("{:4}  {}  ({})".format(r["status"], r["check"], r["detail"]))
    fails = [r["check"] for r in results if r["status"] == "FAIL"]
    summary = {"folder": folder, "page": page, "proposal": proposal, "pass": not fails,
               "checks": len(results), "failed": fails,
               "warnings": [r["check"] for r in results if r["status"] == "WARN"], "results": results}
    print(json.dumps(summary, indent=1, ensure_ascii=False))
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
