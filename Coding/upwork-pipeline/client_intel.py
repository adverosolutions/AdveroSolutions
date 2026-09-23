#!/usr/bin/env python3
"""Client intel: grade an Upwork client and find their first name.

Usage:
    python3 client_intel.py <job_dir> <raw.json>
    python3 client_intel.py --install-js   # the two install scripts (once per snippet version)
    python3 client_intel.py --loader       # the one-line loader to run on each job page

Page side (client_intel/snippet.js, see its header): install once per version
into localStorage["__advero_ci"] of upwork.com with --install-js and the Chrome
tool's file_upload, then run the --loader line on each job page. It returns
the object ({error: "not_installed"} / {error: "stale_install"} means install
again). The main session writes that object to <job>/client_raw.json.

<raw.json> is the object `client_intel/snippet.js` returns on the job page
(the main session saves it as <job_dir>/client_raw.json). This script:

1. writes <job_dir>/client.json: the raw object plus a "derived" block
   (first_name, name_reason, grade, reasons, summary, spend_per_hire);
2. updates <job_dir>/jd.txt in place, inside the metadata paragraph (after the
   title line, before the blank line that precedes the post):
       client first name: <Name>          (only when confident, see below)
       client grade: <A|B|C|D> - <up to 3 short reasons>
   Existing lines are replaced where they sit, so a re-run is idempotent.
   Every other byte of jd.txt stays as it was. The write is atomic;
3. prints one summary line for the batch table, e.g.
       B  Casey  hires often (64%); freelancers praise clear requirements; ...

It refuses (exit 2, jd.txt untouched) when jd.txt is not the fixed shape:
`url: <link>` line, title line, a metadata paragraph of one or more lines, one
blank line, then the post. It also exits 2, touching nothing, when the raw
object reports a page error or a failed parse: the page claims history records
but none parsed, or the About block gave no rating, hires, spend or jobs
posted (the batch carries on without client intel).

First name rule (never guess):
    The snippet counts first names that freelancers use in their comments ABOUT
    the client ("Thank you for the opportunity, Casey."), once per comment,
    never names from the client's own comments, never a word of any
    freelancer's display name, and never company, tool, brand, state or
    common words (see extractNames in the snippet). It marks a name as a
    person when a freelancer addresses it directly ("Thanks Casey") or a
    comment naming only it says he/she. A one-off typo is folded into a more
    frequent name first (the typo has exactly 1 mention, same first two
    letters, edit distance 1 or 2: "Yususf" 1 counts toward "Yusuf" 4). The
    top person name is written only when it has 2 or more mentions AND at
    least twice the count of every other name (person or not).
    Otherwise this script writes no `client first name:` line and removes
    one it wrote on an earlier run. A name line it did not write (the main
    session's, from the post signature or a message) is never touched; the
    summary and client.json "jd_first_name" show that name.

Grade rules (first match wins, D before C before A; B is everything else):
    D = skip. Any of:
        - payment not verified;
        - rating under 4.0 with 5 or more reviews;
        - 2 or more red-flag comments: freelancers' comments about the client
          that match a red-flag phrase ("did not agree", "ended early", "scope",
          "unclear", "unresponsive", "late payment", "dispute", "refund",
          "micromanag", "changed requirements", "low budget", ...) AND carry a
          freelancer rating of the client under 4.5. A flagged phrase inside a
          5-star comment ("the project ended early, but he gave me a heads up")
          is shown in red_flags but does not count toward D;
        - hire rate under 20% with 10 or more jobs posted.
    C = low value. Any of:
        - median fixed price at or under $20 (over 3 or more fixed contracts);
        - spend per hire under $50 (total spent / hires);
        - average hourly paid under $12, unless the median hourly on
          tech/automation titles in the history is $20 or more;
        - no history and no spend: no hires, no history claimed or parsed,
          nothing spent (from the About block, not parsed records alone).
    A = all of: rating 4.8+, hire rate 60%+, spend $10k+, paying well
        (tech-title median hourly $25+ or median contract $300+), and no
        red-flag comment at all (any rating).
    B = everything else.
    Harsh rater cap (after the above): when the client gave freelancers 2 or
    more ratings under 4.5 (harsh_ratings_given), or averaged under 4.5 over 3
    or more ratings given (client_rating_given_avg with client_ratings_n;
    objects from before client_ratings_n existed can only fire the first
    test), the grade is capped at B (an A becomes B; C and D stay)
    and "rates freelancers harshly (3 under 4.5 stars, avg 4.1)" is the FIRST
    reason: a low rating from the client hurts Lorenzo's Job Success Score.

Reasons are short and plain, at most 3: for D and C the triggers that fired;
for A and B how often they hire, what freelancers praise most (clear
requirements first), and what they pay (tech-title hourly range as the 25th to
75th percentile rounded out to $5, plus the average hourly overall).

Everything here is for Lorenzo and the build only. A review fact is never
stated to the client or in the proposal.
"""

import hashlib
import json
import math
import os
import sys
import tempfile
from typing import Any, Dict, List, Optional, Tuple

NAME_KEY = "client first name:"
GRADE_KEY = "client grade:"

SNIPPET_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "client_intel", "snippet.js")
STORE_KEY = "__advero_ci"
INPUT_ID = "__advero_ci_input"
INPUT_LABEL = "advero client intel loader"

PRAISE_LABELS = [
    ("clear_requirements", "clear requirements"),
    ("fast_payment", "fast payment"),
    ("responsive", "quick responses"),
    ("communication", "communication"),
    ("easy_to_work_with", "being easy to work with"),
]


class ShapeError(Exception):
    pass


def _num(v: Any) -> Optional[float]:
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    return None


def _money(v: float) -> str:
    return "$%d" % int(round(v))


def _pct(v: float) -> str:
    return "%d%%" % int(round(v))


def edit_distance(a: str, b: str) -> int:
    """Levenshtein distance (insert, delete, substitute), case-insensitive."""
    a, b = a.lower(), b.lower()
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def merge_name_typos(names: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Fold a one-off typo into a more frequent name: the smaller name has
    exactly 1 mention, same first two letters, edit distance 1 or 2 ("Yususf"
    1 into "Yusuf" 4; "Mary" 2 never folds into "Mark" 3). The merged name is
    a person when either was. An entry without "person" (objects from before
    the flag existed) counts as a person.
    Returns (merged list sorted best first, notes like "Yususf->Yusuf")."""
    ranked = sorted(
        [{"name": n["name"], "count": int(n.get("count") or 0), "person": bool(n.get("person", True))}
         for n in names if isinstance(n, dict) and n.get("name")],
        key=lambda n: (-n["count"], n["name"]),
    )
    kept: List[Dict[str, Any]] = []
    notes: List[str] = []
    for n in ranked:
        target = None
        for k in kept:
            if (n["count"] == 1 and k["count"] > 1 and k["name"][:2].lower() == n["name"][:2].lower()
                    and 1 <= edit_distance(k["name"], n["name"]) <= 2):
                target = k
                break
        if target is None:
            kept.append(dict(n))
        else:
            target["count"] += n["count"]
            target["person"] = target["person"] or n["person"]
            notes.append("%s->%s" % (n["name"], target["name"]))
    kept.sort(key=lambda n: (-n["count"], n["name"]))
    return kept, notes


def decide_name(raw: Dict[str, Any]) -> Tuple[Optional[str], str]:
    """Return (name or None, one-line reason). Typos are merged first. Only a
    name the snippet marked as a person can win; every other name, person or
    not, counts as a runner-up."""
    ranked, notes = merge_name_typos(raw.get("names") or [])
    if not ranked:
        return None, "no first name in freelancers' comments"
    merged = " (merged %s)" % ", ".join(notes) if notes else ""
    people = [n for n in ranked if n["person"]]
    if not people:
        return None, "not confident: %s %d never addressed as a person%s" % (
            ranked[0]["name"], ranked[0]["count"], merged)
    top = people[0]
    top_n = top["count"]
    others = [n["count"] for n in ranked if n is not top]
    runner = max(others) if others else 0
    if top_n >= 2 and top_n >= 2 * runner:
        return top["name"], "%s in %d comments, runner-up %d%s" % (top["name"], top_n, runner, merged)
    return None, "not confident: %s %d vs runner-up %d%s" % (top["name"], top_n, runner, merged)


def spend_per_hire(about: Dict[str, Any]) -> Optional[float]:
    spent = _num(about.get("total_spent_usd"))
    hires = _num(about.get("hires"))
    if spent is None or not hires:
        return None
    return spent / hires


def _pay_reason(raw: Dict[str, Any]) -> Optional[str]:
    about = raw.get("about") or {}
    rates = raw.get("rates") or {}
    avg_hourly = _num(about.get("avg_hourly_paid"))
    tech_n = int(rates.get("tech_hourly_n") or 0)
    p25 = _num(rates.get("tech_hourly_p25"))
    p75 = _num(rates.get("tech_hourly_p75"))
    if tech_n >= 3 and p25 is not None and p75 is not None:
        lo = int(math.floor(p25 / 5.0) * 5)
        hi = int(math.ceil(p75 / 5.0) * 5)
        lo = max(lo, 1)
        span = "$%d/hr" % hi if lo >= hi else "$%d-%d/hr" % (lo, hi)
        text = "pays %s on tech work" % span
        if avg_hourly is not None:
            text += ", %s/hr average overall" % _money(avg_hourly)
        return text
    if avg_hourly is not None:
        return "pays %s/hr on average" % _money(avg_hourly)
    contract = _num(rates.get("contract_median"))
    if contract is not None:
        return "median contract %s" % _money(contract)
    sph = spend_per_hire(about)
    if sph is not None:
        return "about %s per hire" % _money(sph)
    return None


def harsh_rater_reason(raw: Dict[str, Any]) -> Optional[str]:
    """The harsh-rater reason, or None. Rule in the module docstring."""
    harsh = int(raw.get("harsh_ratings_given") or 0)
    given_avg = _num(raw.get("client_rating_given_avg"))
    given_n = _num(raw.get("client_ratings_n"))
    low_avg = given_avg is not None and given_avg < 4.5 and given_n is not None and given_n >= 3
    if harsh < 2 and not low_avg:
        return None
    parts = ["%d under 4.5 stars" % harsh]
    if given_avg is not None:
        parts.append("avg %.1f" % given_avg)
    return "rates freelancers harshly (%s)" % ", ".join(parts)


def grade(raw: Dict[str, Any]) -> Tuple[str, List[str]]:
    """Return (grade letter, up to 3 reasons). Rules in the module docstring."""
    letter, reasons = _base_grade(raw)
    harsh = harsh_rater_reason(raw)
    if harsh:
        if letter == "A":
            letter = "B"
        reasons = [harsh] + reasons
    return letter, reasons[:3]


def _base_grade(raw: Dict[str, Any]) -> Tuple[str, List[str]]:
    about = raw.get("about") or {}
    rates = raw.get("rates") or {}
    rating = _num(about.get("rating"))
    reviews = _num(about.get("reviews")) or 0
    hire_rate = _num(about.get("hire_rate_pct"))
    jobs = _num(about.get("jobs_posted")) or 0
    spent = _num(about.get("total_spent_usd"))
    hires = _num(about.get("hires"))
    avg_hourly = _num(about.get("avg_hourly_paid"))
    history = int(raw.get("history_parsed") or 0)
    claimed = _num(raw.get("history_claimed")) or 0
    flags_low = int(raw.get("red_flag_comments_low_rated") or 0)
    flags_any = int(raw.get("red_flag_comments") or 0)
    tech_median = _num(rates.get("tech_hourly_median"))
    fixed_median = _num(rates.get("fixed_median"))
    fixed_n = int(rates.get("fixed_n") or 0)
    contract_median = _num(rates.get("contract_median"))
    sph = spend_per_hire(about)

    d: List[str] = []
    if about.get("payment_verified") is False:
        d.append("payment not verified")
    if rating is not None and rating < 4.0 and reviews >= 5:
        d.append("rated %.2f by freelancers over %d reviews" % (rating, reviews))
    if flags_low >= 2:
        kinds = []
        for f in raw.get("red_flags") or []:
            k = f.get("k") if isinstance(f, dict) else None
            r = _num(f.get("r")) if isinstance(f, dict) else None
            if k and (r is None or r < 4.5) and k not in kinds:
                kinds.append(k)
        d.append("%d freelancers complain (%s)" % (flags_low, ", ".join(kinds[:2]) or "red flags"))
    if hire_rate is not None and hire_rate < 20 and jobs >= 10:
        d.append("hires rarely (%s of %d jobs)" % (_pct(hire_rate), jobs))
    if d:
        return "D", d[:3]

    c: List[str] = []
    if sph is not None and sph < 50:
        c.append("pays about %s a job across %d %s" % (_money(sph), hires, "hire" if hires == 1 else "hires"))
    if fixed_median is not None and fixed_n >= 3 and fixed_median <= 20:
        c.append("median fixed price %s" % _money(fixed_median))
    if avg_hourly is not None and avg_hourly < 12 and not (tech_median is not None and tech_median >= 20):
        c.append("pays %s/hr on average" % _money(avg_hourly))
    # from the About block and the history count the page claims, not from
    # parsed records alone (a parse that found nothing is refused in run())
    if not hires and not claimed and history == 0 and not spent:
        c.append("no hiring history or spend yet")
    if c:
        return "C", c[:3]

    reasons: List[str] = []
    if hire_rate is not None:
        word = "often" if hire_rate >= 60 else ("sometimes" if hire_rate >= 30 else "rarely")
        reasons.append("hires %s (%s)" % (word, _pct(hire_rate)))
    praise = raw.get("praise") or {}
    for key, label in PRAISE_LABELS:
        if int(praise.get(key) or 0) >= 2:
            reasons.append("freelancers praise %s" % label)
            break
    pay = _pay_reason(raw)
    if pay:
        reasons.append(pay)

    pays_well = (tech_median is not None and tech_median >= 25) or (
        contract_median is not None and contract_median >= 300
    )
    is_a = (
        rating is not None and rating >= 4.8
        and hire_rate is not None and hire_rate >= 60
        and spent is not None and spent >= 10000
        and pays_well
        and flags_any == 0
    )
    return ("A" if is_a else "B"), reasons[:3]


def derive(raw: Dict[str, Any]) -> Dict[str, Any]:
    name, name_reason = decide_name(raw)
    letter, reasons = grade(raw)
    sph = spend_per_hire(raw.get("about") or {})
    return {
        "first_name": name,
        "name_reason": name_reason,
        "grade": letter,
        "reasons": reasons,
        "summary": summary_line(letter, name, reasons),
        "spend_per_hire": round(sph, 2) if sph is not None else None,
    }


def summary_line(letter: str, name: Optional[str], reasons: List[str]) -> str:
    return "%s  %s  %s" % (letter, name or "-", "; ".join(reasons))


def grade_line(derived: Dict[str, Any]) -> str:
    reasons = "; ".join(derived.get("reasons") or [])
    return "%s %s%s" % (GRADE_KEY, derived["grade"], (" - " + reasons) if reasons else "")


def parse_failure(raw: Dict[str, Any]) -> Optional[str]:
    """Why the page object looks like a failed parse, or None. A failed parse
    is refused like a page error: grading it would give a false C."""
    about = raw.get("about") or {}
    claimed = _num(raw.get("history_claimed"))
    parsed = _num(raw.get("history_parsed")) or 0
    if claimed is not None and claimed > 0 and parsed == 0:
        return "the page claims %d history records but none parsed" % claimed
    if all(_num(about.get(k)) is None for k in ("rating", "hires", "total_spent_usd", "jobs_posted")):
        return "the About the client block parsed nothing (no rating, hires, spend or jobs posted)"
    return None


def _is_key(line: str, key: str) -> bool:
    """`client first name:` / `Client First Name:` alike."""
    return line[:len(key)].lower() == key


def _is_blank(line: str) -> bool:
    return line.strip() == ""


def split_jd(text: str) -> Tuple[List[str], int]:
    """Return (lines with endings, index of the blank line). Raises ShapeError."""
    lines = text.splitlines(True)
    if len(lines) < 5:
        raise ShapeError("jd.txt is too short: expected url line, title line, metadata paragraph, one blank line, post")
    if not lines[0].startswith("url: "):
        raise ShapeError("jd.txt line 1 must start with 'url: '")
    if _is_blank(lines[1]):
        raise ShapeError("jd.txt line 2 must be the job title")
    blank = None
    for i in range(2, len(lines)):
        if _is_blank(lines[i]):
            blank = i
            break
    if blank is None:
        raise ShapeError("jd.txt has no blank line between the metadata paragraph and the post")
    if blank == 2:
        raise ShapeError("jd.txt has no metadata paragraph between the title line and the blank line")
    if blank + 1 >= len(lines) or _is_blank(lines[blank + 1]):
        raise ShapeError("jd.txt must have exactly one blank line followed by the post")
    return lines, blank


def _value(line: str, key: str) -> str:
    return line[len(key):].strip()


def existing_name(text: str) -> Optional[str]:
    lines, blank = split_jd(text)
    for l in lines[2:blank]:
        if _is_key(l, NAME_KEY):
            return _value(l, NAME_KEY) or None
    return None


def update_jd_text(text: str, name: Optional[str], grade_text: str, keep_name: bool = False) -> str:
    """Return jd text with the client lines set. Raises ShapeError.

    Each line is replaced where it already sits (duplicates dropped) or, when
    absent, appended to the end of the metadata paragraph, name before grade.
    Keys match case-insensitively. name=None removes the name line, unless
    keep_name is set (the first name line was written by the main session, not
    by this script, and is left exactly as is; later name lines are dropped).
    """
    lines, blank = split_jd(text)
    nl = "\r\n" if lines[1].endswith("\r\n") else "\n"
    meta: List[str] = []
    name_done = keep_name
    grade_done = False
    kept_first = False
    for l in lines[2:blank]:
        if _is_key(l, NAME_KEY):
            if keep_name:
                if not kept_first:
                    meta.append(l)
                    kept_first = True
            elif name and not name_done:
                meta.append("%s %s%s" % (NAME_KEY, name, nl))
                name_done = True
            continue
        if _is_key(l, GRADE_KEY):
            if not grade_done:
                meta.append(grade_text + nl)
                grade_done = True
            continue
        meta.append(l)
    tail: List[str] = []
    if name and not name_done:
        tail.append("%s %s%s" % (NAME_KEY, name, nl))
    if not grade_done:
        tail.append(grade_text + nl)
    if grade_done and tail:
        # keep the name line ahead of an existing grade line
        gi = [i for i, l in enumerate(meta) if _is_key(l, GRADE_KEY)][0]
        meta[gi:gi] = tail
        tail = []
    return "".join(lines[:2] + meta + tail + lines[blank:])


def atomic_write(path: str, data: str) -> None:
    d = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=d)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(data)
        try:
            os.chmod(tmp, os.stat(path).st_mode & 0o777)
        except OSError:
            pass
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _previous_written_name(client_path: str) -> Optional[str]:
    """The name this script wrote last time. A client.json from before
    "name_written" existed only has "first_name"; that version wrote the
    first name whenever it had one, so it stands in."""
    try:
        with open(client_path, encoding="utf-8") as fh:
            prev = json.load(fh)
        derived = prev.get("derived") or {}
        if "name_written" in derived:
            return derived.get("name_written")
        return derived.get("first_name")
    except (OSError, ValueError, AttributeError):
        return None


def run(job_dir: str, raw_path: str) -> str:
    jd_path = os.path.join(job_dir, "jd.txt")
    client_path = os.path.join(job_dir, "client.json")
    if not os.path.isfile(jd_path):
        raise ShapeError("no jd.txt in %s" % job_dir)
    with open(raw_path, encoding="utf-8") as fh:
        raw = json.load(fh)
    if not isinstance(raw, dict):
        raise ValueError("raw.json is not an object")
    if raw.get("error"):
        raise ValueError("page returned error '%s'; jd.txt unchanged, carry on without client intel" % raw["error"])
    if not isinstance(raw.get("about"), dict):
        raise ValueError("raw.json has no 'about' object; jd.txt unchanged")
    failed = parse_failure(raw)
    if failed:
        raise ValueError("parse failed: %s; jd.txt unchanged, carry on without client intel" % failed)
    derived = derive(raw)
    with open(jd_path, encoding="utf-8", newline="") as fh:
        old = fh.read()
    # A name line this script did not write (the post signature, a message) is
    # the main session's and wins over the reviews: it is left exactly as is.
    current = existing_name(old)  # also validates the shape before any write
    keep = current is not None and current != _previous_written_name(client_path)
    new = update_jd_text(old, derived["first_name"], grade_line(derived), keep_name=keep)
    derived["name_written"] = None if keep else derived["first_name"]
    derived["jd_first_name"] = current if keep else derived["first_name"]
    if keep and derived["first_name"] and derived["first_name"] != current:
        derived["name_reason"] += "; jd.txt already names %s, kept" % current
    derived["summary"] = summary_line(derived["grade"], derived["jd_first_name"], derived["reasons"])
    out = dict(raw)
    out["derived"] = derived
    atomic_write(client_path, json.dumps(out, indent=2, ensure_ascii=False) + "\n")
    if new != old:
        atomic_write(jd_path, new)
    return derived["summary"]


def snippet_version(path: str = SNIPPET_PATH) -> str:
    """First 12 hex chars of sha256 of snippet.js: the install version."""
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()[:12]


def install_js(path: str = SNIPPET_PATH) -> Tuple[str, str]:
    """The two install scripts: (add the file input, read + verify + store)."""
    v = snippet_version(path)
    add = (
        '(() => { const old = document.getElementById("%s"); if (old) old.remove(); '
        'const i = document.createElement("input"); i.type = "file"; i.id = "%s"; '
        'i.setAttribute("aria-label", "%s"); '
        'i.style.cssText = "position:fixed;top:8px;left:8px;z-index:2147483647;background:#fff"; '
        'document.body.appendChild(i); return "input added: file_upload snippet.js into \\"%s\\""; })()'
    ) % (INPUT_ID, INPUT_ID, INPUT_LABEL, INPUT_LABEL)
    store = (
        'await (async (want) => { const i = document.getElementById("%s"); '
        'if (!i || !i.files || !i.files[0]) return {error: "no_file"}; const f = i.files[0]; '
        'const hash = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", await f.arrayBuffer())))'
        '.map((b) => b.toString(16).padStart(2, "0")).join("").slice(0, 12); '
        'if (hash !== want) return {error: "wrong_file", have: hash, want: want}; '
        'const src = await f.text(); '
        'localStorage.setItem("%s", JSON.stringify({v: hash, src: src})); '
        'localStorage.removeItem("__advero_ci_src"); i.remove(); '
        'return {ok: true, v: hash, chars: src.length}; })("%s")'
    ) % (INPUT_ID, STORE_KEY, v)
    return add, store


def loader_js(path: str = SNIPPET_PATH) -> str:
    """One line, run on each job page; evaluates to the object (never a string)."""
    v = snippet_version(path)
    return (
        'await (async (want, o) => { try { o = JSON.parse(localStorage.getItem("%s")); } catch (e) {} '
        'return !o || !o.src ? {error: "not_installed", want: want} '
        ': o.v !== want ? {error: "stale_install", have: o.v, want: want} '
        ': (async () => {}).constructor("__ADVERO_CI_NO_AUTORUN", o.src + "\\nreturn __clientIntel.runInPage();")(1); '
        '})("%s")'
    ) % (STORE_KEY, v)


def install_text() -> str:
    add, store = install_js()
    return "\n".join([
        "# Install client intel %s (once per snippet version, on any upwork.com page)" % snippet_version(),
        "# 1. javascript tool (%d chars):" % len(add),
        add,
        '# 2. find the input labelled "%s" and file_upload this path into it:' % INPUT_LABEL,
        SNIPPET_PATH,
        "# 3. javascript tool (%d chars); expect {ok: true, v: \"%s\"}:" % (len(store), snippet_version()),
        store,
    ])


def main(argv: List[str]) -> int:
    if len(argv) == 2 and argv[1] == "--install-js":
        print(install_text())
        return 0
    if len(argv) == 2 and argv[1] == "--loader":
        print(loader_js())
        return 0
    if len(argv) != 3:
        sys.stderr.write("usage: python3 client_intel.py <job_dir> <raw.json> | --install-js | --loader\n")
        return 2
    try:
        print(run(argv[1], argv[2]))
    except (ShapeError, ValueError, OSError) as exc:
        sys.stderr.write("client_intel: refused: %s\n" % exc)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
