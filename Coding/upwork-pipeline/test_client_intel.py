"""Tests for client_intel/snippet.js (parser, run through node) and client_intel.py.

Run: cd <pipeline root> && python3 -m pytest -q test_client_intel.py
Fixtures in client_intel/fixtures/ are anonymized page text (document.body.innerText
from "About the client" onward, after expanding the history).
"""

import json
import os
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SNIPPET = os.path.join(HERE, "client_intel", "snippet.js")
FIXTURES = os.path.join(HERE, "client_intel", "fixtures")
SCRIPT = os.path.join(HERE, "client_intel.py")
sys.path.insert(0, HERE)

import client_intel as ci  # noqa: E402

NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node is not installed; the snippet parser tests need node")

# Loads the snippet outside the page: the file ends in a
# top-level `await`, so it is evaluated as the body of an async function, with
# `module` supplied so the parser is exported. `document` is undefined, so the
# browser part never runs.
NODE_LOADER = r"""
const fs = require("fs");
const src = fs.readFileSync(process.argv[1], "utf8");
const AsyncFunction = (async () => {}).constructor;
const m = { exports: {} };
AsyncFunction("module", "require", src)(m, require).then((last) => {
  const text = fs.readFileSync(process.argv[2], "utf8");
  process.stdout.write(JSON.stringify({ last: last, out: m.exports.parseClientIntel(text) }));
});
"""


def parse_file(path):
    res = subprocess.run(
        [NODE, "-e", NODE_LOADER, SNIPPET, path],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=60,
    )
    assert res.returncode == 0, res.stderr
    data = json.loads(res.stdout)
    assert data.get("last") is None  # the browser branch did not run
    return data["out"]


def parse_text(tmp_path, text):
    p = tmp_path / "page.txt"
    p.write_text(text, encoding="utf-8")
    return parse_file(str(p))


def fixture(name):
    return os.path.join(FIXTURES, name)


def walk_sizes(v, acc):
    if isinstance(v, str):
        acc["str"] = max(acc["str"], len(v))
    elif isinstance(v, list):
        acc["arr"] = max(acc["arr"], len(v))
        for x in v:
            walk_sizes(x, acc)
    elif isinstance(v, dict):
        for x in v.values():
            walk_sizes(x, acc)
    return acc


def assert_compact(out):
    sizes = walk_sizes(out, {"str": 0, "arr": 0})
    assert sizes["str"] < 800
    assert sizes["arr"] < 40
    assert len(json.dumps(out, separators=(",", ":"))) < 5000


# ---------------------------------------------------------------- parser (node)

@needs_node
def test_hourly_fixture_parse():
    out = parse_file(fixture("hourly_named_client.txt"))
    assert_compact(out)
    a = out["about"]
    assert a["rating"] == 4.99 and a["reviews"] == 102
    assert a["payment_verified"] is True and a["phone_verified"] is True
    assert a["badges"] == ["Pays on time", "Experienced client"]
    assert a["country"] == "United States" and a["city"] == "Plainview"
    assert a["jobs_posted"] == 217 and a["hire_rate_pct"] == 64 and a["open_jobs"] == 2
    assert a["total_spent_usd"] == 76000 and a["hires"] == 190 and a["active"] == 30
    assert a["avg_hourly_paid"] == 10.05 and a["hours"] == 7111
    assert a["industry"] == "Sales & Marketing"
    assert a["company_size"] == "Mid-sized company (10-99 people)"
    assert a["member_since"] == "Apr 1, 2018"
    assert out["history_claimed"] == 50
    assert out["history_parsed"] == 39
    assert out["names"][0] == {"name": "Casey", "count": 9, "person": True}
    assert {"name": "Sam", "count": 2, "person": True} in out["names"]
    assert {"name": "Alex", "count": 1, "person": False} in out["names"]
    assert len(out["names"]) == 3  # nothing else slipped through the stopwords
    assert out["freelancer_names"] > 20
    assert out["fl_rating_avg"] == 5.0
    assert out["harsh_ratings_given"] == 1  # the 4.3 given to one freelancer
    assert out["client_ratings_n"] == 31
    kinds = [f["k"] for f in out["red_flags"]]
    assert kinds == ["ended early", "did not agree"]
    assert out["red_flag_comments"] == 2 and out["red_flag_comments_low_rated"] == 0
    assert out["praise"]["clear_requirements"] >= 3
    r = out["rates"]
    assert r["hourly_n"] == 39 and r["fixed_n"] == 0 and r["hourly_median"] == 20
    assert r["tech_hourly_n"] == 14 and r["tech_hourly_median"] == 22.5
    assert 0 < r["share_le_20"] < 0.2
    assert 1 <= len(out["client_voice"]) <= 3 and all(len(s) <= 120 for s in out["client_voice"])
    assert 1 <= len(out["fl_quotes"]) <= 4 and all(len(s) <= 140 for s in out["fl_quotes"])


@needs_node
def test_fixed_fixture_parse():
    out = parse_file(fixture("fixed_unnamed_client.txt"))
    assert_compact(out)
    a = out["about"]
    assert a["rating"] == 5.0 and a["reviews"] == 510
    assert a["city"] == "Dana Point" and a["jobs_posted"] == 590
    assert a["hire_rate_pct"] == 92 and a["open_jobs"] == 41
    assert a["total_spent_usd"] == 5700 and a["hires"] == 548 and a["active"] == 10
    assert a["avg_hourly_paid"] is None and a["hours"] is None
    assert a["industry"] == "HR & Business Services"
    assert out["history_claimed"] == 50 and out["history_parsed"] == 8
    assert out["names"] == []
    r = out["rates"]
    assert r["hourly_n"] == 0 and r["fixed_n"] == 7 and r["fixed_median"] == 12
    assert r["share_le_20"] == 1


@needs_node
def test_no_history_fixture_parse():
    out = parse_file(fixture("no_history_client.txt"))
    assert_compact(out)
    assert out["about"]["payment_verified"] is False
    assert out["about"]["jobs_posted"] == 1 and out["about"]["hire_rate_pct"] == 0
    assert out["history_parsed"] == 0 and out["history_claimed"] is None
    assert out["names"] == [] and out["fl_rating_avg"] is None


@needs_node
def test_names_only_from_freelancer_comments(tmp_path):
    page = "\n".join([
        "About the client", "5.00 of 3 reviews", "Payment verified", "United States", "Austin3:12 PM",
        "Client's recent history (3)",
        "Job one",
        "Rating is 5.0 out of 5.", "5.0",
        "Thanks Robin, great project. Working with Parker was fun too.",
        "To freelancer: Parker Q.",
        "Rating is 5.0 out of 5.", "5.0",
        "Taylor was great, thank you Taylor.",
        "Jan 2026 - Jan 2026", "Fixed-price $100.00",
        "Job two",
        "Rating is 5.0 out of 5.", "5.0",
        "Robin was clear and kind.",
        "To freelancer: Morgan Z.No feedback given",
        "Feb 2026 - Feb 2026", "Fixed-price $100.00",
        "Job three",
        "No feedback given",
        "To freelancer: Jamie B.",
        "Rating is 4.0 out of 5.", "4.0",
        "Jamie delivered late.",
        "Mar 2026 - Mar 2026", "5 hrs @ $40.00/hr", "Billed: $200.00",
        "Footer navigation",
    ])
    out = parse_text(tmp_path, page)
    names = {n["name"]: n["count"] for n in out["names"]}
    # Parker is a freelancer's first name; Taylor only appears in a client's comment.
    assert names == {"Robin": 2}
    assert out["history_parsed"] == 3
    assert out["harsh_ratings_given"] == 1
    assert out["rates"]["contract_median"] == 100


@needs_node
def test_compact_limits_on_huge_page(tmp_path):
    rec = [
        "Automation developer needed",
        "Rating is 5.0 out of 5.", "5.0",
        "Great client, clear requirements and fast payment. " * 30,
        "To freelancer: Avery Q.",
        "Rating is 5.0 out of 5.", "5.0",
        "Avery was excellent and I would hire again. " * 30,
        "Jan 2026 - Jan 2026", "10 hrs @ $30.00/hr", "Billed: $300.00",
    ]
    page = ["About the client", "4.90 of 200 reviews", "Payment verified", "United States", "Austin3:12 PM",
            "Client's recent history (200)"] + rec * 200 + ["Footer navigation"]
    out = parse_text(tmp_path, "\n".join(page))
    assert out["history_parsed"] == 200
    assert_compact(out)


# ---------------------------------------------------------------- name + grade

@needs_node
def test_hourly_fixture_name_and_grade():
    raw = parse_file(fixture("hourly_named_client.txt"))
    d = ci.derive(raw)
    assert d["first_name"] == "Casey"
    assert d["grade"] == "B"
    assert d["reasons"] == [
        "hires often (64%)",
        "freelancers praise clear requirements",
        "pays $15-30/hr on tech work, $10/hr average overall",
    ]
    assert d["summary"].startswith("B  Casey  hires often (64%)")


@needs_node
def test_fixed_fixture_name_and_grade():
    raw = parse_file(fixture("fixed_unnamed_client.txt"))
    d = ci.derive(raw)
    assert d["first_name"] is None
    assert d["grade"] == "C"
    assert d["reasons"][0] == "pays about $10 a job across 548 hires"
    assert d["summary"].startswith("C  -  pays about $10 a job across 548 hires")


@needs_node
def test_no_history_fixture_grade():
    raw = parse_file(fixture("no_history_client.txt"))
    d = ci.derive(raw)
    assert d["grade"] == "D" and d["reasons"][0] == "payment not verified"
    raw["about"]["payment_verified"] = True
    d = ci.derive(raw)
    assert d["grade"] == "C" and "no hiring history or spend yet" in d["reasons"]


def base_raw(**about):
    a = {"rating": 4.9, "reviews": 40, "payment_verified": True, "hire_rate_pct": 70,
         "jobs_posted": 50, "total_spent_usd": 40000, "hires": 60, "avg_hourly_paid": 30}
    a.update(about)
    return {"about": a, "history_parsed": 20, "names": [], "red_flags": [],
            "red_flag_comments": 0, "red_flag_comments_low_rated": 0,
            "praise": {"clear_requirements": 0, "fast_payment": 3},
            "rates": {"tech_hourly_median": 35, "tech_hourly_p25": 30, "tech_hourly_p75": 45,
                      "tech_hourly_n": 6, "contract_median": 800, "fixed_median": None, "fixed_n": 0}}


def test_grade_a_and_b():
    g, reasons = ci.grade(base_raw())
    assert g == "A"
    assert reasons == ["hires often (70%)", "freelancers praise fast payment",
                       "pays $30-45/hr on tech work, $30/hr average overall"]
    raw = base_raw()
    raw["red_flag_comments"] = 1
    assert ci.grade(raw)[0] == "B"
    assert ci.grade(base_raw(total_spent_usd=9000))[0] == "B"


def test_grade_d_rules():
    assert ci.grade(base_raw(rating=3.8, reviews=6)) == ("D", ["rated 3.80 by freelancers over 6 reviews"])
    assert ci.grade(base_raw(rating=3.8, reviews=4))[0] == "B"  # too few reviews for D, too low for A
    assert ci.grade(base_raw(hire_rate_pct=10, jobs_posted=12))[1] == ["hires rarely (10% of 12 jobs)"]
    raw = base_raw()
    raw["red_flag_comments"] = raw["red_flag_comments_low_rated"] = 2
    raw["red_flags"] = [{"k": "dispute", "r": 2.0, "t": "..."}, {"k": "refund", "r": 3.0, "t": "..."}]
    assert ci.grade(raw) == ("D", ["2 freelancers complain (dispute, refund)"])


def test_grade_c_rules():
    g, reasons = ci.grade(base_raw(avg_hourly_paid=9))
    assert g == "A"  # tech-title median $35 overrides the low average
    raw = base_raw(avg_hourly_paid=9)
    raw["rates"]["tech_hourly_median"] = 15
    assert ci.grade(raw) == ("C", ["pays $9/hr on average"])
    raw = base_raw()
    raw["rates"].update({"fixed_median": 15, "fixed_n": 5})
    assert ci.grade(raw) == ("C", ["median fixed price $15"])
    raw["rates"].update({"fixed_n": 2})
    assert ci.grade(raw)[0] == "A"


def test_name_decision():
    def raw(*pairs):
        return {"names": [{"name": n, "count": c} for n, c in pairs]}
    assert ci.decide_name(raw(("Casey", 9), ("Sam", 2)))[0] == "Casey"
    assert ci.decide_name(raw(("Casey", 4), ("Sam", 2)))[0] == "Casey"
    assert ci.decide_name(raw(("Casey", 3), ("Sam", 2)))[0] is None
    assert ci.decide_name(raw(("Casey", 1)))[0] is None
    assert ci.decide_name(raw(("Casey", 2)))[0] == "Casey"
    assert ci.decide_name(raw())[0] is None


# ---------------------------------------------------------------- jd.txt

JD = (
    "url: https://www.upwork.com/jobs/~01\n"
    "Build an n8n Workflow\n"
    "Fixed price $500, expert. Client in Texas.\n"
    "Prop: n8n build.\n"
    "\n"
    "We need an n8n workflow.\n"
    "\n"
    "client grade: this line is part of the post and must stay\n"
)


def make_job(tmp_path, jd=JD, name="job"):
    d = tmp_path / name
    d.mkdir()
    (d / "jd.txt").write_bytes(jd.encode("utf-8"))
    return d


def write_raw(tmp_path, raw):
    p = tmp_path / "client_raw.json"
    p.write_text(json.dumps(raw), encoding="utf-8")
    return str(p)


def run_cli(job, raw_path):
    return subprocess.run([sys.executable, SCRIPT, str(job), raw_path],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)


def named_raw():
    raw = base_raw()
    raw["names"] = [{"name": "Casey", "count": 5}, {"name": "Sam", "count": 1}]
    return raw


def test_jd_update_idempotent_and_byte_faithful(tmp_path):
    job = make_job(tmp_path)
    raw_path = write_raw(tmp_path, named_raw())
    r1 = run_cli(job, raw_path)
    assert r1.returncode == 0, r1.stderr
    assert r1.stdout.startswith("A  Casey  hires often (70%)")
    after1 = (job / "jd.txt").read_bytes()
    expected = JD.replace(
        "Prop: n8n build.\n",
        "Prop: n8n build.\nclient first name: Casey\nclient grade: A - hires often (70%); "
        "freelancers praise fast payment; pays $30-45/hr on tech work, $30/hr average overall\n",
    ).encode("utf-8")
    assert after1 == expected
    r2 = run_cli(job, raw_path)
    assert r2.returncode == 0
    assert (job / "jd.txt").read_bytes() == after1
    client = json.loads((job / "client.json").read_text(encoding="utf-8"))
    assert client["derived"]["grade"] == "A" and client["derived"]["first_name"] == "Casey"
    assert client["about"]["hire_rate_pct"] == 70


def test_jd_rerun_replaces_and_removes_name(tmp_path):
    job = make_job(tmp_path)
    run_cli(job, write_raw(tmp_path, named_raw()))
    raw = named_raw()
    raw["names"] = [{"name": "Casey", "count": 2}, {"name": "Sam", "count": 2}]
    raw["about"]["payment_verified"] = False
    assert run_cli(job, write_raw(tmp_path, raw)).returncode == 0
    text = (job / "jd.txt").read_text(encoding="utf-8")
    assert "client first name:" not in text
    assert text.count("client grade: D - payment not verified\n") == 1
    assert text.endswith("\nclient grade: this line is part of the post and must stay\n")


def test_jd_keeps_crlf_and_existing_manual_name(tmp_path):
    # A name line the main session wrote (post signature) is never replaced.
    jd = JD.replace("Prop: n8n build.\n", "client first name: Jo\nProp: n8n build.\n").replace("\n", "\r\n")
    job = make_job(tmp_path, jd)
    raw_path = write_raw(tmp_path, named_raw())
    r = run_cli(job, raw_path)
    assert r.returncode == 0, r.stderr
    assert r.stdout.startswith("A  Jo  ")
    out = (job / "jd.txt").read_bytes()
    expected = jd.replace(
        "Prop: n8n build.\r\n",
        "Prop: n8n build.\r\nclient grade: A - hires often (70%); "
        "freelancers praise fast payment; pays $30-45/hr on tech work, $30/hr average overall\r\n",
    ).encode("utf-8")
    assert out == expected
    derived = json.loads((job / "client.json").read_text(encoding="utf-8"))["derived"]
    assert derived["first_name"] == "Casey" and derived["jd_first_name"] == "Jo"
    assert derived["name_written"] is None and "kept" in derived["name_reason"]
    assert run_cli(job, raw_path).returncode == 0
    assert (job / "jd.txt").read_bytes() == expected


def test_jd_own_name_line_updated_in_place(tmp_path):
    job = make_job(tmp_path)
    run_cli(job, write_raw(tmp_path, named_raw()))
    raw = named_raw()
    raw["names"] = [{"name": "Robin", "count": 4}]
    assert run_cli(job, write_raw(tmp_path, raw)).returncode == 0
    text = (job / "jd.txt").read_text(encoding="utf-8")
    assert "client first name: Robin\nclient grade: A - " in text
    assert "Casey" not in text


@pytest.mark.parametrize("bad", [
    "Build an n8n Workflow\nmeta\n\npost\n",                                   # no url line
    "url: x\nTitle\nmeta\npost with no blank line\nmore\n",                   # no blank line
    "url: x\nTitle\nmeta\n\n\npost after two blank lines\n",                   # two blank lines
    "url: x\nTitle\n\npost\nmore post\n",                                      # no metadata paragraph
    "url: x\n\nmeta\n\npost\n",                                                # no title
])
def test_shape_refusal(tmp_path, bad):
    job = make_job(tmp_path, bad)
    r = run_cli(job, write_raw(tmp_path, named_raw()))
    assert r.returncode == 2
    assert "refused" in r.stderr
    assert (job / "jd.txt").read_bytes() == bad.encode("utf-8")
    assert not (job / "client.json").exists()


def test_page_error_refusal(tmp_path):
    job = make_job(tmp_path)
    r = run_cli(job, write_raw(tmp_path, {"v": 1, "error": "challenge", "title": "Just a moment..."}))
    assert r.returncode == 2 and "challenge" in r.stderr
    assert (job / "jd.txt").read_bytes() == JD.encode("utf-8")
    assert not (job / "client.json").exists()


@needs_node
def test_end_to_end_on_fixture(tmp_path):
    raw = parse_file(fixture("hourly_named_client.txt"))
    job = make_job(tmp_path)
    r = run_cli(job, write_raw(tmp_path, raw))
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == ("B  Casey  hires often (64%); freelancers praise clear requirements; "
                                "pays $15-30/hr on tech work, $10/hr average overall")
    text = (job / "jd.txt").read_text(encoding="utf-8")
    assert "client first name: Casey\nclient grade: B - hires often (64%)" in text


# A stand-in page: just enough DOM for runInPage (wait, one "View more" click,
# parse). The first innerText read has no history; the click reveals it.
FAKE_PAGE = r"""
const fs = require("fs");
const src = fs.readFileSync(process.argv[1], "utf8");
const full = fs.readFileSync(process.argv[2], "utf8");
const cut = full.indexOf("Client's recent history");
let expanded = false;
let clicks = 0;
const head = { children: [], textContent: "Client's recent history (50)",
               compareDocumentPosition: () => 4 };
const button = { innerText: "View more", offsetParent: {}, disabled: false,
                 getClientRects: () => [1], click: () => { clicks += 1; expanded = true; } };
globalThis.Node = { DOCUMENT_POSITION_FOLLOWING: 4, DOCUMENT_POSITION_PRECEDING: 2 };
globalThis.location = { href: "https://www.upwork.com/jobs/~01?referrer=x" };
globalThis.document = {
  title: "Job page",
  get body() { return { innerText: "Nav\n" + (expanded ? full : full.slice(0, cut) + "Client's recent history (50)\n") }; },
  querySelectorAll: (sel) => sel.startsWith("h1") ? [head] : (expanded ? [] : [button]),
};
const AsyncFunction = (async () => {}).constructor;
const m = { exports: {} };
AsyncFunction("module", "require", src)(m, require).then(() =>
  m.exports.runInPage()
).then((out) => process.stdout.write(JSON.stringify({ clicks: clicks, out: out })));
"""


@needs_node
def test_run_in_page_with_fake_dom():
    res = subprocess.run(
        [NODE, "-e", FAKE_PAGE, SNIPPET, fixture("hourly_named_client.txt")],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=120,
    )
    assert res.returncode == 0, res.stderr
    data = json.loads(res.stdout)
    # the file's own last line ran runInPage (one click expands the history);
    # the test's second run finds no button left
    assert data["clicks"] == 1
    out = data["out"]
    assert out["url"] == "https://www.upwork.com/jobs/~01"
    assert out["history_parsed"] == 39
    assert out["names"][0]["name"] == "Casey"
    assert_compact(out)


# ---------------------------------------------------------------- live object

def test_live_raw_object_end_to_end(tmp_path):
    """The object snippet.js returned on a real fixed-price job page (anonymized)."""
    raw_path = fixture("live_fixed_client_raw.json")
    with open(raw_path, encoding="utf-8") as fh:
        raw = json.load(fh)
    assert_compact(raw)
    assert raw["history_parsed"] == 48 and raw["expand_clicks"] == 10
    job = make_job(tmp_path)
    r = run_cli(job, raw_path)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "C  Jamie  pays about $10 a job across 548 hires; median fixed price $10"
    text = (job / "jd.txt").read_text(encoding="utf-8")
    assert ("Prop: n8n build.\nclient first name: Jamie\n"
            "client grade: C - pays about $10 a job across 548 hires; median fixed price $10\n\n") in text
    first = (job / "jd.txt").read_bytes()
    assert run_cli(job, raw_path).returncode == 0
    assert (job / "jd.txt").read_bytes() == first


# ---------------------------------------------------------------- install + loader

def test_install_and_loader_text():
    import hashlib
    with open(SNIPPET, "rb") as fh:
        v = hashlib.sha256(fh.read()).hexdigest()[:12]
    assert ci.snippet_version() == v
    loader = ci.loader_js()
    assert "\n" not in loader and len(loader) < 600 and '("%s")' % v in loader
    assert "JSON.stringify" not in loader  # returns the object, never a string
    add, store = ci.install_js()
    assert 'aria-label", "advero client intel loader"' in add and '("%s")' % v in store
    r = subprocess.run([sys.executable, SCRIPT, "--loader"], stdout=subprocess.PIPE, universal_newlines=True)
    assert r.returncode == 0 and r.stdout == loader + "\n"
    r = subprocess.run([sys.executable, SCRIPT, "--install-js"], stdout=subprocess.PIPE, universal_newlines=True)
    lines = r.stdout.splitlines()
    assert r.returncode == 0 and add in lines and store in lines and SNIPPET in lines


# Fake upwork.com page with localStorage, a file input the "file_upload" fills,
# and the job page from the hourly fixture. Each tool call is evaluated like
# the javascript tool does: one expression, top-level await allowed.
LOADER_PAGE = r"""
const fs = require("fs");
const cfg = JSON.parse(fs.readFileSync(process.argv[1], "utf8"));
const full = fs.readFileSync(cfg.fixture, "utf8");
const store = {};
globalThis.localStorage = {
  getItem: (k) => (k in store ? store[k] : null),
  setItem: (k, v) => { store[k] = String(v); },
  removeItem: (k) => { delete store[k]; },
};
const nodes = {};
let clicks = 0, expanded = false;
const head = { children: [], textContent: "Client's recent history (50)", compareDocumentPosition: () => 4 };
const button = { innerText: "View more", offsetParent: {}, getClientRects: () => [1],
                 click: () => { clicks += 1; expanded = true; } };
const cut = full.indexOf("Client's recent history");
globalThis.Node = { DOCUMENT_POSITION_FOLLOWING: 4, DOCUMENT_POSITION_PRECEDING: 2 };
globalThis.location = { href: "https://www.upwork.com/jobs/~01" };
globalThis.document = {
  title: "Job page",
  get body() {
    return { innerText: expanded ? full : full.slice(0, cut) + "Client's recent history (50)\n",
             appendChild: (el) => { nodes[el.id] = el; } };
  },
  getElementById: (id) => nodes[id] || null,
  createElement: (tag) => {
    const el = { tag: tag, style: {}, attrs: {}, files: null };
    el.setAttribute = (k, v) => { el.attrs[k] = v; };
    el.remove = () => { delete nodes[el.id]; };
    return el;
  },
  querySelectorAll: (sel) => sel.startsWith("h1") ? [head] : (expanded ? [] : [button]),
};
const AF = (async () => {}).constructor;
const tool = (code) => new AF("return " + code)();
function upload(path) {
  const buf = fs.readFileSync(path);
  const el = Object.values(nodes).find((n) => n.attrs["aria-label"] === "advero client intel loader");
  el.files = [{ text: async () => buf.toString("utf8"),
                arrayBuffer: async () => buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength) }];
}
(async () => {
  const out = {};
  out.before = await tool(cfg.loader);
  store["__advero_ci_src"] = "old test key";
  out.add = await tool(cfg.add);
  upload(cfg.tampered);
  out.wrong = await tool(cfg.store);
  upload(cfg.snippet);
  out.store = await tool(cfg.store);
  out.input_left = Object.keys(nodes).length;
  out.old_key_left = "__advero_ci_src" in store;
  out.stored_v = JSON.parse(store["__advero_ci"]).v;
  out.run = await tool(cfg.loader);
  out.run_type = typeof out.run;
  out.clicks = clicks;
  out.stale = await tool(cfg.loader_other);
  process.stdout.write(JSON.stringify(out));
})();
"""


@needs_node
def test_loader_path_in_fake_page(tmp_path):
    add, store = ci.install_js()
    loader = ci.loader_js()
    other = loader.replace('("%s")' % ci.snippet_version(), '("000000000000")')
    tampered = tmp_path / "snippet.js"
    tampered.write_text(open(SNIPPET, encoding="utf-8").read() + "\n// edited\n", encoding="utf-8")
    cfg = tmp_path / "cfg.json"
    cfg.write_text(json.dumps({
        "fixture": fixture("hourly_named_client.txt"), "snippet": SNIPPET, "tampered": str(tampered),
        "add": add, "store": store, "loader": loader, "loader_other": other,
    }), encoding="utf-8")
    res = subprocess.run([NODE, "-e", LOADER_PAGE, str(cfg)], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         universal_newlines=True, timeout=120)
    assert res.returncode == 0, res.stderr
    out = json.loads(res.stdout)
    v = ci.snippet_version()
    assert out["before"] == {"error": "not_installed", "want": v}
    assert out["add"].startswith("input added")
    assert out["wrong"]["error"] == "wrong_file" and out["wrong"]["want"] == v
    assert out["store"]["ok"] is True and out["store"]["v"] == v
    assert out["input_left"] == 0 and out["old_key_left"] is False and out["stored_v"] == v
    assert out["run_type"] == "object"
    run = out["run"]
    assert run["history_parsed"] == 39 and run["names"][0] == {"name": "Casey", "count": 9, "person": True}
    assert run["expand_clicks"] == 1 and out["clicks"] == 1  # the stored copy did not auto-run too
    assert_compact(run)
    assert out["stale"] == {"error": "stale_install", "have": v, "want": "000000000000"}


# ---------------------------------------------------------------- harsh rater + name typos

def test_live_harsh_rater_end_to_end(tmp_path):
    """Real object (anonymized): 4.11 average given, 3 ratings under 4.5, a name typo."""
    raw_path = fixture("live_harsh_client_raw.json")
    job = make_job(tmp_path)
    r = run_cli(job, raw_path)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == ("B  Dana  rates freelancers harshly (3 under 4.5 stars, avg 4.1); "
                                "hires often (100%); freelancers praise communication")
    derived = json.loads((job / "client.json").read_text(encoding="utf-8"))["derived"]
    assert "merged Danna->Dana" in derived["name_reason"] and "Dana in 5 comments" in derived["name_reason"]


def test_harsh_rater_caps_a_and_leads_reasons():
    raw = base_raw()
    assert ci.grade(raw)[0] == "A"
    raw["harsh_ratings_given"], raw["client_rating_given_avg"] = 2, 4.6
    g, reasons = ci.grade(raw)
    assert g == "B" and reasons[0] == "rates freelancers harshly (2 under 4.5 stars, avg 4.6)"
    assert len(reasons) == 3
    # average rule needs 3 or more ratings given, and the count
    raw = base_raw()
    raw["harsh_ratings_given"], raw["client_rating_given_avg"] = 1, 4.3
    assert ci.grade(raw)[0] == "A"  # no client_ratings_n: average rule cannot fire
    raw["client_ratings_n"] = 2
    assert ci.grade(raw)[0] == "A"
    raw["client_ratings_n"] = 3
    assert ci.grade(raw)[1][0] == "rates freelancers harshly (1 under 4.5 stars, avg 4.3)"
    # C and D keep their letter, the reason still leads
    raw = base_raw(avg_hourly_paid=9)
    raw["rates"]["tech_hourly_median"] = 15
    raw["harsh_ratings_given"], raw["client_rating_given_avg"] = 3, 4.1
    assert ci.grade(raw) == ("C", ["rates freelancers harshly (3 under 4.5 stars, avg 4.1)",
                                   "pays $9/hr on average"])


def test_name_typo_merge():
    def raw(*pairs):
        return {"names": [{"name": n, "count": c} for n, c in pairs]}
    assert ci.decide_name(raw(("Yusuf", 4), ("Yususf", 1)))[0] == "Yusuf"
    # a one-off typo folds in and can tip the 2x test (Casey 4 vs Sam 2)
    name, why = ci.decide_name(raw(("Casey", 3), ("Cassey", 1), ("Sam", 2)))
    assert name == "Casey" and "Cassey->Casey" in why
    merged, _ = ci.merge_name_typos([{"name": "Casey", "count": 3}, {"name": "Cassey", "count": 1}])
    assert merged == [{"name": "Casey", "count": 4, "person": True}]
    # a smaller name with 2 or more mentions is a different person: never merged
    assert len(ci.merge_name_typos([{"name": "Casey", "count": 3}, {"name": "Cassey", "count": 2}])[0]) == 2
    # equal counts, different first two letters, or distance 3 never merge
    assert len(ci.merge_name_typos([{"name": "Casey", "count": 2}, {"name": "Cassey", "count": 2}])[0]) == 2
    assert len(ci.merge_name_typos([{"name": "Casey", "count": 3}, {"name": "Kasey", "count": 1}])[0]) == 2
    assert len(ci.merge_name_typos([{"name": "Jordan", "count": 3}, {"name": "Joe", "count": 1}])[0]) == 2
    assert ci.edit_distance("Yusuf", "Yususf") == 1 and ci.edit_distance("Jordan", "Joe") == 4


# ---------------------------------------------------------------- review 2 regressions
# Every reproduction from the second review (/private/tmp/claude-501/review_ci/adv/)
# lives here: name cases in fixtures/review_name_cases.json (same page layout
# as the reviewer's harness), the three end-to-end pages in
# fixtures/review_page_*.txt.

NODE_MANY = r"""
const fs = require("fs");
const src = fs.readFileSync(process.argv[1], "utf8");
const AsyncFunction = (async () => {}).constructor;
const m = { exports: {} };
AsyncFunction("module", "require", src)(m, require).then(() => {
  const texts = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
  process.stdout.write(JSON.stringify(texts.map((t) => m.exports.parseClientIntel(t))));
});
"""


def parse_many(tmp_path, texts):
    p = tmp_path / "pages.json"
    p.write_text(json.dumps(texts), encoding="utf-8")
    res = subprocess.run([NODE, "-e", NODE_MANY, SNIPPET, str(p)], stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, universal_newlines=True, timeout=120)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout)


def review_page(records, about=None):
    """The reviewer's harness page: records are {fl, to, cl, title, flr, clr}."""
    lines = about or ["About the client", "5.00 of 20 reviews", "Payment verified", "United States",
                      "Austin3:12 PM", "20 jobs posted", "80% hire rate, 1 open job", "$20K total spent",
                      "20 hires, 2 active"]
    lines = list(lines) + ["Client's recent history (%d)" % len(records)]
    for i, r in enumerate(records):
        lines.append(r.get("title") or "Project number %d" % i)
        if r.get("fl") is not None:
            lines += ["Rating is %s out of 5." % r.get("flr", "5.0"), r.get("flr", "5.0"), r["fl"]]
        else:
            lines.append("No feedback given")
        lines.append("To freelancer: " + r.get("to", "Zed Q."))
        if r.get("cl") is not None:
            lines += ["Rating is %s out of 5." % r.get("clr", "5.0"), r.get("clr", "5.0"), r["cl"]]
        else:
            lines.append("No feedback given")
        lines += ["Jan 2026 - Feb 2026", r.get("pay", "Fixed-price $500.00")]
    lines.append("Footer navigation")
    return "\n".join(lines)


with open(fixture("review_name_cases.json"), encoding="utf-8") as _fh:
    REVIEW_NAME_CASES = json.load(_fh)

# words the first review wrote as a client name: none may even be counted
NEVER_COUNTED = {"Smith", "Webflow", "Bro", "Brother", "Guys", "Boss", "Inc", "Wish", "Texas", "Claude",
                 "Ahmed", "Priya", "Payment", "Feedback", "Lumora", "Jos", "Andr", "Chlo"}


@needs_node
def test_review_name_cases(tmp_path):
    outs = parse_many(tmp_path, [review_page(c["records"]) for c in REVIEW_NAME_CASES])
    got = {}
    for c, out in zip(REVIEW_NAME_CASES, outs):
        name, why = ci.decide_name(out)
        got[c["label"]] = name
        counted = {n["name"] for n in out["names"]}
        assert not (counted & NEVER_COUNTED), (c["label"], counted)
    assert got == {c["label"]: c["expect"] for c in REVIEW_NAME_CASES}
    by_label = dict(zip([c["label"] for c in REVIEW_NAME_CASES], outs))
    # a company name nobody addresses as a person is counted, never written
    assert by_label["company name"]["names"] == [{"name": "Brightpath", "count": 2, "person": False}]
    # typo merge: Mark 3 / Mary 2 stay apart and neither is confident
    assert {(n["name"], n["count"]) for n in by_label["typo merge Mark/Mary"]["names"]} == {("Mark", 3), ("Mary", 2)}


@needs_node
def test_accented_names_whole(tmp_path):
    pages = [
        review_page([{"fl": "Thank you José! Great project.", "to": "Ann B."},
                     {"fl": "Thanks José, smooth work.", "to": "Cid D."}]),
        review_page([{"fl": "Thank you Zoë.", "to": "Ann B."},
                     {"fl": "It was a pleasure, thanks Zoë!", "to": "Cid D."}]),
        review_page([{"fl": "Thanks André, great client.", "to": "Ann B."},
                     {"fl": "André was clear and he paid fast.", "to": "Cid D."}]),
        # NFD: e + combining acute accent
        review_page([{"fl": "Thanks José!", "to": "Ann B."}, {"fl": "Thank you José.", "to": "Cid D."}]),
        # a freelancer named José: never the client's name
        review_page([{"fl": "Thanks José, great client.", "to": "José R."},
                     {"fl": "Thanks José for everything.", "to": "José R."}]),
    ]
    outs = parse_many(tmp_path, pages)
    assert [(n["name"], n["count"]) for n in outs[0]["names"]] == [("José", 2)]
    assert [(n["name"], n["count"]) for n in outs[1]["names"]] == [("Zoë", 2)]
    assert [(n["name"], n["count"]) for n in outs[2]["names"]] == [("André", 2)]
    assert [(n["name"], n["count"]) for n in outs[3]["names"]] == [("José", 2)]
    assert outs[4]["names"] == []
    assert [ci.decide_name(o)[0] for o in outs] == ["José", "Zoë", "André", "José", None]


@needs_node
def test_name_rules_titles_suffixes_honorifics(tmp_path):
    pages = [
        # a tool named in a job title is never a name
        review_page([{"fl": "Thanks Retool, great work.", "to": "Ann B.", "title": "Retool dashboard build"},
                     {"fl": "Thank you Retool.", "to": "Cid D."}]),
        # a word before a company suffix
        review_page([{"fl": "Thanks Nimbus, great client.", "to": "Ann B."},
                     {"fl": "The Nimbus team was great, thank you Nimbus.", "to": "Cid D."}]),
        # a surname after an honorific, even when later thanked
        review_page([{"fl": "Thanks Mrs. Lopez, great client.", "to": "Ann B."},
                     {"fl": "Dr. Lopez was clear. Thanks Lopez!", "to": "Cid D."}]),
        # lowercase "miss" is a verb, not an honorific
        review_page([{"fl": "Thanks Casey, I will miss Casey and this project.", "to": "Ann B."},
                     {"fl": "Thank you Casey!", "to": "Cid D."}]),
        # a real name next to all of the above still wins
        review_page([{"fl": "Thanks Casey, and the Nimbus team.", "to": "Ann B."},
                     {"fl": "Casey was clear, he paid fast.", "to": "Cid D.", "title": "Retool dashboard"},
                     {"fl": "Thank you Casey!", "to": "Eve F."}]),
    ]
    outs = parse_many(tmp_path, pages)
    assert outs[0]["names"] == [] and outs[1]["names"] == [] and outs[2]["names"] == []
    assert outs[3]["names"] == [{"name": "Casey", "count": 2, "person": True}]
    assert outs[4]["names"] == [{"name": "Casey", "count": 3, "person": True}]
    assert ci.decide_name(outs[4])[0] == "Casey"


@needs_node
@pytest.mark.parametrize("page,jd_before,summary", [
    ("review_page_jose.txt", "client first name: Jos\n", "A  José  hires often (80%)"),
    ("review_page_mr.txt", "client first name: Smith\n", "A  -  hires often (80%)"),
    ("review_page_company.txt", "client first name: Brightpath\n", "A  -  hires often (80%)"),
])
def test_review_pages_end_to_end(tmp_path, page, jd_before, summary):
    # jd.txt as the first review left it: a wrong name this script wrote
    jd = JD.replace("Prop: n8n build.\n", "Prop: n8n build.\n" + jd_before)
    job = make_job(tmp_path, jd)
    (job / "client.json").write_text(json.dumps({"derived": {"first_name": _value_of(jd_before),
                                                              "name_written": _value_of(jd_before)}}))
    raw = parse_file(fixture(page))
    r = run_cli(job, write_raw(tmp_path, raw))
    assert r.returncode == 0, r.stderr
    assert r.stdout.startswith(summary)
    text = (job / "jd.txt").read_text(encoding="utf-8")
    name = summary.split()[1]
    if name == "-":
        assert "client first name:" not in text
    else:
        assert text.count("client first name:") == 1 and ("client first name: %s\n" % name) in text


def _value_of(line):
    return line.split(":", 1)[1].strip()


PRAISE_PAGE_ABOUT = ["About the client", "4.60 of 12 reviews", "Payment verified", "United States", "Austin3:12 PM",
                     "20 jobs posted", "50% hire rate, 1 open job", "$6K total spent", "10 hires, 1 active",
                     "$25.00 /hr avg hourly rate paid"]


def praise_page(pairs):
    return review_page([{"fl": c, "flr": r, "to": "Zed%s Q." % chr(65 + i), "cl": "ok",
                         "title": "Data entry task %d" % i, "pay": "Fixed-price $300.00"}
                        for i, (r, c) in enumerate(pairs)], about=PRAISE_PAGE_ABOUT)


@needs_node
def test_praise_and_flags_respect_negation(tmp_path):
    complaints = praise_page([
        ("3.0", "The client gave unclear instructions."),
        ("3.0", "Very unresponsive client."),
        ("3.0", "Not very responsive."),
        ("3.0", "Lack of communication made this hard."),
        ("3.0", "Communication could be much better."),
        ("3.0", "Communication was not great and replies were slow."),
    ])
    negated_flags = praise_page([
        ("5.0", "Paid fast, never late, no scope creep and no disputes."),
        ("5.0", "Not unclear at all, never had a dispute, no refund needed."),
        ("5.0", "Never ghosted, never micromanaged."),
    ])
    genuine_praise = praise_page([
        ("5.0", "Clear instructions and great communication."),
        ("5.0", "Very responsive and paid fast."),
        ("5.0", "Communication was smooth, requirements were clear."),
    ])
    genuine_flags = praise_page([
        ("2.0", "He kept changing the scope and opened a dispute."),
        ("2.0", "Unclear requirements and unresponsive."),
        ("3.0", "Payment was late, we did not agree on the refund."),
    ])
    c, n, p, f = parse_many(tmp_path, [complaints, negated_flags, genuine_praise, genuine_flags])
    assert all(v == 0 for v in c["praise"].values()), c["praise"]
    assert c["red_flag_comments"] == 3  # unclear, unresponsive, not very responsive
    assert n["red_flag_comments"] == 0 and n["red_flags"] == []
    assert n["praise"]["fast_payment"] == 1
    assert p["praise"]["clear_requirements"] == 2 and p["praise"]["communication"] == 2
    assert p["praise"]["responsive"] == 1 and p["praise"]["fast_payment"] == 1
    assert p["red_flag_comments"] == 0
    assert f["red_flag_comments"] == 3 and f["red_flag_comments_low_rated"] == 3
    assert [x["k"] for x in f["red_flags"]] == ["scope", "unclear", "did not agree"]
    assert all(v == 0 for v in f["praise"].values()), f["praise"]
    # "Lack of communication" no longer earns "freelancers praise communication"
    assert not any("praise" in reason for reason in ci.grade(c)[1])
    # the negated-flags client can still be an A: no red flag at any rating
    assert ci.grade(n)[0] != "D"


@needs_node
def test_harsh_average_fires_from_page_text(tmp_path):
    about = ["About the client", "4.90 of 40 reviews", "Payment verified", "United States", "Austin3:12 PM",
             "50 jobs posted", "70% hire rate, 1 open job", "$40K total spent", "60 hires, 2 active",
             "$30.00 /hr avg hourly rate paid"]
    recs = [{"title": "Automation developer %d" % i, "fl": "Great client, clear requirements and fast payment.",
             "to": "Zed%s Q." % chr(65 + i), "cl": "ok", "clr": "%.1f" % cr,
             "pay": "100 hrs @ $40.00/hr"} for i, cr in enumerate([5, 5, 5, 1])]
    out = parse_many(tmp_path, [review_page(recs, about=about)])[0]
    assert out["client_ratings_n"] == 4 and out["client_rating_given_avg"] == 4.0
    assert out["harsh_ratings_given"] == 1
    g, reasons = ci.grade(out)
    assert g == "B"
    assert reasons[0] == "rates freelancers harshly (1 under 4.5 stars, avg 4.0)"


def parse_failure_raw(**over):
    raw = {"v": 1, "about": {"rating": None, "reviews": None, "payment_verified": True, "hires": None,
                             "total_spent_usd": None, "jobs_posted": None, "hire_rate_pct": None},
           "history_claimed": 30, "history_parsed": 0, "names": [], "red_flags": [], "praise": {}, "rates": {}}
    raw.update(over)
    return raw


@pytest.mark.parametrize("raw,why", [
    (parse_failure_raw(), "claims 30 history records but none parsed"),
    (parse_failure_raw(about=base_raw()["about"]), "claims 30 history records but none parsed"),
    (parse_failure_raw(history_claimed=None), "About the client block parsed nothing"),
])
def test_parse_failure_refused(tmp_path, raw, why):
    # the first review's repro graded this C "no hiring history or spend yet"
    job = make_job(tmp_path)
    r = run_cli(job, write_raw(tmp_path, raw))
    assert r.returncode == 2
    assert "parse failed" in r.stderr and why in r.stderr
    assert (job / "jd.txt").read_bytes() == JD.encode("utf-8")
    assert not (job / "client.json").exists()


@needs_node
def test_parse_failure_from_page_text_refused(tmp_path):
    # the page claims 30 records, but the history text is in a shape the parser does not know
    page = "\n".join(["About the client", "Client's recent history (30)", "Something unexpected",
                      "Footer navigation"])
    raw = parse_text(tmp_path, page)
    assert raw["history_claimed"] == 30 and raw["history_parsed"] == 0
    assert ci.parse_failure(raw)
    job = make_job(tmp_path)
    assert run_cli(job, write_raw(tmp_path, raw)).returncode == 2
    assert (job / "jd.txt").read_bytes() == JD.encode("utf-8")


def test_no_history_decided_from_about():
    # hires in the About block: not "no history", even with no parsed records
    raw = base_raw(total_spent_usd=None, hires=3)
    raw["history_parsed"] = 0
    assert "no hiring history or spend yet" not in ci.grade(raw)[1]
    raw = base_raw(total_spent_usd=None, hires=None, avg_hourly_paid=None)
    raw["history_parsed"], raw["history_claimed"] = 0, None
    assert ci.grade(raw) == ("C", ["no hiring history or spend yet"])
    raw["history_claimed"] = 2
    assert "no hiring history or spend yet" not in ci.grade(raw)[1]


def test_one_hire_reads_singular():
    g, reasons = ci.grade(base_raw(total_spent_usd=30, hires=1))
    assert g == "C" and reasons[0] == "pays about $30 a job across 1 hire"
    assert ci.grade(base_raw(total_spent_usd=60, hires=2))[1][0] == "pays about $30 a job across 2 hires"


def test_name_key_case_insensitive(tmp_path):
    # the main session wrote "Client first name:"; a buggy earlier run added a second line
    jd = JD.replace("Prop: n8n build.\n", "Client first name: Jo\nProp: n8n build.\nclient first name: Casey\n")
    job = make_job(tmp_path, jd)
    (job / "client.json").write_text(json.dumps({"derived": {"first_name": "Casey", "name_written": "Casey"}}))
    r = run_cli(job, write_raw(tmp_path, named_raw()))
    assert r.returncode == 0, r.stderr
    assert r.stdout.startswith("A  Jo  ")
    text = (job / "jd.txt").read_text(encoding="utf-8")
    assert text.lower().count("client first name:") == 1 and "Client first name: Jo\n" in text
    # no conflicting second line on a fresh job either, and the grade key matches any case
    jd = JD.replace("Prop: n8n build.\n", "Client First Name: Jo\nClient Grade: old\n")
    job2 = make_job(tmp_path, jd, name="job2")
    assert run_cli(job2, write_raw(tmp_path, named_raw())).returncode == 0
    text = (job2 / "jd.txt").read_text(encoding="utf-8")
    assert text.lower().count("client first name:") == 1 and "Client First Name: Jo\nclient grade: A - " in text
    assert "Client Grade: old" not in text


def test_legacy_client_json_name_is_ours(tmp_path):
    # a client.json from before name_written: its first_name line was ours
    jd = JD.replace("Prop: n8n build.\n", "Prop: n8n build.\nclient first name: Robin\n")
    job = make_job(tmp_path, jd)
    (job / "client.json").write_text(json.dumps({"about": {}, "derived": {"first_name": "Robin", "grade": "A"}}))
    r = run_cli(job, write_raw(tmp_path, named_raw()))
    assert r.returncode == 0, r.stderr
    text = (job / "jd.txt").read_text(encoding="utf-8")
    assert "client first name: Casey\n" in text and "Robin" not in text
    # and a later run with no confident name removes it
    raw = named_raw()
    raw["names"] = []
    assert run_cli(job, write_raw(tmp_path, raw)).returncode == 0
    assert "client first name:" not in (job / "jd.txt").read_text(encoding="utf-8")
    # a legacy client.json whose first_name differs from the line: the line is the main session's
    jd = JD.replace("Prop: n8n build.\n", "Prop: n8n build.\nclient first name: Jo\n")
    job2 = make_job(tmp_path, jd, name="job2")
    (job2 / "client.json").write_text(json.dumps({"derived": {"first_name": "Robin"}}))
    assert run_cli(job2, write_raw(tmp_path, named_raw())).returncode == 0
    assert "client first name: Jo\n" in (job2 / "jd.txt").read_text(encoding="utf-8")


# A fake page for the "View more" clicker. Document order (pos): 1 history
# heading, 2 the history's own "View more" button (reveals `reveal` more
# records per click, `stages` times), then extra elements from the config:
# a "View more similar jobs" <a href> below the history, optionally an end
# marker heading and a button after it. No "Other open jobs by this Client".
CLICK_PAGE = r"""
const fs = require("fs");
const src = fs.readFileSync(process.argv[1], "utf8");
const cfg = JSON.parse(process.argv[2]);
const log = [];
let stage = 0;
function el(pos, props) {
  return Object.assign({ pos: pos, children: [], offsetParent: {}, getClientRects: () => [1], disabled: false,
    compareDocumentPosition(o) { return o.pos > this.pos ? 4 : (o.pos < this.pos ? 2 : 0); } }, props);
}
const head = el(1, { textContent: "Client's recent history (9)" });
const histBtn = el(2, { tag: "button", innerText: "View more",
  click() { log.push("history"); if (stage < cfg.stages) { stage += 1; } } });
const link = el(3, { tag: "a", innerText: "View more similar jobs",
  getAttribute: (k) => (k === "href" ? "https://www.upwork.com/nx/search/jobs/?q=similar" : null),
  href: "https://www.upwork.com/nx/search/jobs/?q=similar", click() { log.push("LINK"); } });
const endHead = el(4, { textContent: "Similar jobs on Upwork" });
const lateBtn = el(5, { tag: "button", innerText: "View more", click() { log.push("AFTER END"); } });
function record(i) {
  return ["Job " + i, "Rating is 5.0 out of 5.", "5.0", "Great client.", "To freelancer: Zed" + i + " Q.",
          "No feedback given", "Jan 2026 - Feb 2026", "Fixed-price $500.00"].join("\n");
}
globalThis.Node = { DOCUMENT_POSITION_FOLLOWING: 4, DOCUMENT_POSITION_PRECEDING: 2 };
globalThis.location = { href: "https://www.upwork.com/jobs/~01" };
globalThis.document = {
  title: "Job page",
  get body() {
    const n = cfg.base + stage * cfg.reveal;
    const recs = []; for (let i = 0; i < n; i++) { recs.push(record(i)); }
    return { innerText: ["About the client", "Payment verified", "5 jobs posted", "Client's recent history (9)"]
      .concat(recs).concat(cfg.endMarker ? ["Similar jobs on Upwork"] : []).concat(["Footer navigation"]).join("\n") };
  },
  querySelectorAll: (sel) => {
    if (sel.startsWith("h1")) { return cfg.endMarker ? [head, endHead] : [head]; }
    const out = [];
    if (stage < cfg.stages || cfg.keepButton) { out.push(histBtn); }
    out.push(link);
    if (cfg.endMarker) { out.push(lateBtn); }
    return out;
  },
};
const AF = (async () => {}).constructor; const m = { exports: {} };
AF("module", "require", "var __ADVERO_CI_NO_AUTORUN = 1;\n" + src)(m, require).then(() => m.exports.runInPage())
  .then((out) => process.stdout.write(JSON.stringify({ log: log, clicks: out.expand_clicks, parsed: out.history_parsed })));
"""


def click_page(cfg):
    res = subprocess.run([NODE, "-e", CLICK_PAGE, SNIPPET, json.dumps(cfg)], stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, universal_newlines=True, timeout=120)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout)


@needs_node
def test_view_more_never_follows_a_link_without_end_heading():
    # the reviewer's page: no "Other open jobs" heading, a navigating link below the history
    out = click_page({"base": 3, "reveal": 3, "stages": 2, "endMarker": False, "keepButton": False})
    assert out["log"] == ["history", "history"] and out["clicks"] == 2 and out["parsed"] == 9


@needs_node
def test_view_more_stops_when_a_click_adds_nothing():
    # fakedom.js: the history button stays but adds no record; the link is never clicked
    out = click_page({"base": 0, "reveal": 0, "stages": 0, "endMarker": False, "keepButton": True})
    assert out["log"] == ["history"] and out["clicks"] == 1


@needs_node
def test_view_more_bounded_by_parser_end_markers():
    # a "View more" button after "Similar jobs on Upwork" is outside the history
    out = click_page({"base": 3, "reveal": 3, "stages": 1, "endMarker": True, "keepButton": False})
    assert out["log"] == ["history"] and out["clicks"] == 1 and out["parsed"] == 6
