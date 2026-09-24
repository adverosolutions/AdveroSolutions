"""Instantly copy change-set library: doc text -> staged sequences -> PATCH.

Pure functions only; nothing here talks to the network. build_from_doc.py and
apply_instantly_copy.py wire these together.

The doc tools (tools/template_doc/parse_doc.py and diff_doc.py) are imported,
not reimplemented, and so are phase0_lib's HTML <-> text conversion, tag
parser and offers.md figure checks, and copy_validator's spin-variable check.

Python 3.9 compatible.
"""
import copy
import difflib
import hashlib
import json
import os
import re
import sys
import tempfile
from typing import Any, Dict, List, Optional, Set, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
TEMPLATE_DOC_DIR = os.path.join(ROOT, "tools", "template_doc")
for _p in (ROOT, TEMPLATE_DOC_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import diff_doc  # noqa: E402  (tools/template_doc)
import parse_doc  # noqa: E402  (tools/template_doc)
from changesets.instantly_phase0 import phase0_lib as L  # noqa: E402
from services.experiments.copy_validator import variables_inside_spins  # noqa: E402

TOOL = "instantly_copy/build_from_doc"
DOC_ID = "1jTg1ccYJT8CugDdCf3BQHqzgHUKC4oFG9rgolUILO4U"
DEFAULT_MANIFEST = os.path.join(TEMPLATE_DOC_DIR, "manifest.json")
# Drive's export of the doc as uploaded: the source of the doc's own structure
# lines (headings, section titles, notes), see structure_lines().
REFERENCE_EXPORT = os.path.join(TEMPLATE_DOC_DIR, "drive_export.txt")
STAGED_ROOT = os.path.join(HERE, "staged")
TAG_PREFIX = "instantly."
TAG_RE = re.compile(r"^instantly\.([a-z][a-z0-9_]*)\.step(\d+)(/subject)?$")
CAMPAIGN_FILE_RE = re.compile(r"^[a-z][a-z0-9_]*\.json$")
FIELDS = ("body", "subject")

# What a lead would see literally if Lorenzo typed the engine's placeholder
# style into an Instantly email: Instantly only substitutes {{name}}.
SINGLE_BRACE_RE = re.compile(r"\{[^{}]*\}")
SQUARE_PLACEHOLDER_RE = re.compile(r"\[\s*[A-Za-z_][A-Za-z0-9_ ]*\s*\]")

# The doc router's note rule (tools/template_doc/route_doc.py NOTE_MARK_RE and
# NOTE_START_RE; a test pins that these stay equal). Copied, not imported, so a
# change-set that PATCHes live copy never depends on a file another tool edits.
NOTE_MARK_RE = re.compile(r"\(\s*note\s*\)", re.IGNORECASE)
NOTE_START_RE = re.compile(r"^\s*NOTE\b", re.IGNORECASE)
# The doc's grey markers; any fragment of one inside a block means a marker
# line was merged into the copy.
MARKER_RE = re.compile(r"\(\s*(?:tag\s*:|section\s*\)|note\s*\))", re.IGNORECASE)

# Dash-like characters that are not a plain hyphen, plus "--" typed as a dash.
DASH_CHARS = {
    u"‒": "figure dash", u"–": "en dash", u"—": "em dash", u"―": "horizontal bar",
    u"−": "minus sign", u"⸺": "two-em dash", u"⸻": "three-em dash", u"﹘": "small em dash",
    u"﹣": "small hyphen-minus", u"－": "full-width hyphen-minus", u"⸗": "double oblique hyphen",
    u"〜": "wave dash", u"〰": "wavy dash",
}
EXCLAMATION_CHARS = {
    u"!": "exclamation mark", u"！": "full-width exclamation mark", u"‼": "double exclamation mark",
    u"⁉": "exclamation question mark", u"❗": "exclamation mark emoji",
    u"❕": "white exclamation mark emoji", u"¡": "inverted exclamation mark",
    u"﹗": "small exclamation mark", u"❢": "heavy exclamation mark ornament",
}

# Time windows. Every NEW numeric time window in an edited text is refused
# unless the campaign's config/offers.md row / proof line allows that window
# (phase0_lib.allowed_offer_numbers) or the old text already had it: a changed
# guarantee window ("in the first 60 days") or case-study window ("in just 60
# days") is a changed promise, whatever words surround it. Numbers may be
# digits or words ("sixty days"); units day/week/month/year, spaced or
# hyphenated ("60-day"). The ONLY exemptions are the non-promise shapes in
# WINDOW_EXEMPT_RES, each pinned by a test:
#   * "N days/weeks/months/years ago"             (the past)
#   * "for [over|more than|almost|nearly] N years" (tenure, years only)
#   * "N years in business" / "N years of experience" (tenure)
# Anything else, "next 2 weeks" included, is refused; Lorenzo rephrases.
_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100,
}
_TENS = "twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety"
_UNITS_WORDS = "one|two|three|four|five|six|seven|eight|nine"
_NUM = r"(?:\d+|(?:%s)[\s-](?:%s)|%s)" % (_TENS, _UNITS_WORDS, "|".join(sorted(_NUMBER_WORDS, key=len, reverse=True)))
WINDOW_RE = re.compile(r"\b(%s)\+?[\s-]+(day|week|month|year)s?\b" % _NUM, re.I)
WINDOW_EXEMPT_RES = (
    re.compile(r"\b%s\+?[\s-]+(?:day|week|month|year)s?\s+ago\b" % _NUM, re.I),
    re.compile(r"\bfor\s+(?:over\s+|more\s+than\s+|almost\s+|nearly\s+)?%s\+?\s+years?\b" % _NUM, re.I),
    re.compile(r"\b%s\+?\s+years?\s+(?:in\s+business|of\s+experience)\b" % _NUM, re.I),
)


def _number(word: str) -> int:
    w = re.sub(r"[\s-]+", " ", word.strip().lower())
    if w.isdigit():
        return int(w)
    if " " in w:
        a, b = w.split(" ", 1)
        return _NUMBER_WORDS[a] + _NUMBER_WORDS[b]
    return _NUMBER_WORDS[w]


def time_windows(text: str) -> List[Tuple[str, str, bool]]:
    """[(phrase with context, "60 day", exempt)] for every numeric time window.
    The key matches phase0_lib.period_phrases' format ("90 day")."""
    exempt_spans = [m.span() for r in WINDOW_EXEMPT_RES for m in r.finditer(text)]
    out = []
    for m in WINDOW_RE.finditer(text):
        key = "%d %s" % (_number(m.group(1)), m.group(2).lower())
        exempt = any(a <= m.start() and m.end() <= b for a, b in exempt_spans)
        a = max(0, m.start() - 25)
        phrase = ("..." if a else "") + text[a:m.end() + 15].replace("\n", " ") + "..."
        out.append((phrase, key, exempt))
    return out


class BuildError(ValueError):
    pass


# ------------------------------------------------------------------ io
def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def read_export(path: str) -> str:
    with open(path, "rb") as fh:
        return fh.read().decode("utf-8-sig")


def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def dumps(data: Any) -> str:
    """The exact bytes a staged file holds (the apply side compares them)."""
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def write_json(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(dumps(data))
    os.replace(tmp, path)


def resolve(path: str) -> str:
    """Recorded paths are relative to the code root unless absolute."""
    return path if os.path.isabs(path) else os.path.join(ROOT, path)


def rel(path: str) -> str:
    p = os.path.abspath(path)
    return os.path.relpath(p, ROOT) if p.startswith(ROOT + os.sep) else p


def _inside(path: str, root: str) -> bool:
    return path.startswith(root.rstrip(os.sep) + os.sep)


def out_dir_allowed(out_dir: str) -> bool:
    """A staged folder lives strictly inside changesets/instantly_copy/staged/,
    or inside the system temp dir (tests). Never config/, changesets/backups/
    or anywhere else a replace could delete real files."""
    real = os.path.realpath(out_dir)
    return any(_inside(real, os.path.realpath(r)) for r in allowed_out_roots())


def allowed_out_roots() -> Tuple[str, ...]:
    return (STAGED_ROOT, tempfile.gettempdir())


# ------------------------------------------------------------------ doc text
def body_text_from_doc(text: str) -> str:
    """The doc block as the plain text Instantly's body holds.

    Drive's text/plain export writes every paragraph gap as TWO blank lines
    (drive_export.txt); the manifest, and the live bodies, have one. So lines
    are right-stripped, runs of blank lines collapse to one, and blank edges go.
    Nothing else changes: no quote, dash or wording fix. For all twelve
    Instantly bodies in drive_export.txt this gives exactly the manifest text
    (test_instantly_copy.py pins it)."""
    out = []  # type: List[str]
    for line in text.replace("\r", "").split("\n"):
        line = line.rstrip()
        if not line and (not out or not out[-1]):
            continue
        out.append(line)
    while out and not out[-1]:
        out.pop()
    return "\n".join(out)


def body_html_from_doc(text: str) -> str:
    return L.text_to_html(body_text_from_doc(text))


def subject_from_doc(text: str) -> str:
    return text.strip()


def doc_value(field: str, text: str) -> str:
    return body_html_from_doc(text) if field == "body" else subject_from_doc(text)


def doc_text(field: str, text: str) -> str:
    return body_text_from_doc(text) if field == "body" else subject_from_doc(text)


def parse_tag(tag: str) -> Optional[Tuple[str, int, str]]:
    """(campaign_key, step, field) for an instantly.* tag, else None."""
    m = TAG_RE.match(tag)
    if not m:
        return None
    return m.group(1), int(m.group(2)), "subject" if m.group(3) else "body"


def format_notes(old_html: str, old_text: str) -> List[str]:
    """What regenerating an edited body from text changes besides the words:
    the four live bodies whose HTML does not round-trip through text."""
    if L.text_to_html(old_text) == old_html:
        return []
    notes = []
    if re.search(u"\u00a0+ *</div>", old_html):
        notes.append("formatting-only change: trailing non-breaking spaces removed")
    elif re.search(r" +</div>", old_html):
        notes.append("formatting-only change: trailing spaces removed")
    if re.search(r"<div><br\s*/?>[^<]", old_html):
        notes.append("formatting-only change: a line break inside a line becomes a blank line of its own "
                     "(renders the same)")
    if not notes:
        notes.append("formatting-only change: the original HTML does not round-trip through plain text")
    return notes


# ------------------------------------------------------------------ structure
def structure_lines(manifest: Dict[str, Any], reference_export: str = REFERENCE_EXPORT) -> Set[str]:
    """The doc's own non-copy lines, normalised with diff_doc.norm: every
    manifest heading and label, and every line of the doc as uploaded that is
    not inside a block (the top section, section titles, notes, heading lines
    without their tag). A changed Instantly block holding one of these means a
    grey marker was deleted and the structure line ran into the copy."""
    out = set()  # type: Set[str]
    for b in manifest.get("blocks", []):
        for k in ("heading", "label"):
            v = b.get(k)
            if isinstance(v, str) and diff_doc.norm(v):
                out.add(diff_doc.norm(v))
    if not os.path.exists(reference_export):
        return out
    cur = None
    for line in parse_doc.split_lines(read_export(reference_export)):
        tags = list(parse_doc.TAG_RE.finditer(line))
        if tags:
            tag = tags[-1].group(1)
            if tag.lower().endswith("/subject"):
                continue
            rest = parse_doc.TAG_RE.sub(u"", line)
            cur = tag
        elif parse_doc.SECTION_RE.search(line):
            rest = parse_doc.SECTION_RE.sub(u"", line)
            cur = None
        elif parse_doc.NOTE_RE.search(line):
            rest = parse_doc.NOTE_RE.sub(u"", line)
        elif cur is None:
            rest = line
        else:
            continue
        if diff_doc.norm(rest):
            out.add(diff_doc.norm(rest))
    return out


# ------------------------------------------------------------------ copy rules
def check_copy(field: str, old: str, new: str, known_vars: Optional[Set[str]], campaign_key: str,
               offer: Optional[str], offers_md: str, structure: Set[str]) -> Tuple[List[str], List[str]]:
    """(errors, warnings) for a changed doc block ``new`` (raw doc text).

    phase0's validators (phase0_lib.validate_sequence and the stricter
    services.experiments.copy_validator.validate_copy) judge a whole staged
    3-step A/B sequence (3-5 spin points, variants A and B, offers.md proof line
    verbatim) that the live 2-step, 1-variant campaigns do not have, so they
    would refuse every edit. This applies the per-text hard rules instead,
    built from their pieces. It reports; it never rewrites."""
    errs = []  # type: List[str]
    warns = []  # type: List[str]
    text = doc_text(field, new)
    old_text = doc_text(field, old)

    # notes for Claude and doc structure that ran into the copy (never stripped)
    old_lines = set(diff_doc.norm(l) for l in old_text.split("\n"))
    for line in new.split("\n"):
        if diff_doc.norm(line) in old_lines:
            continue  # already in the live copy: it is copy, whatever it looks like
        if NOTE_MARK_RE.search(line) or NOTE_START_RE.match(line):
            errs.append("holds a note, not email copy: %r (move notes out of the email, or tell Claude in chat)"
                        % line.strip())
        elif MARKER_RE.search(line):
            errs.append("holds a doc marker (tag/section/note): %r; a grey marker line ran into the email"
                        % line.strip())
        elif diff_doc.norm(line) and diff_doc.norm(line) in structure:
            errs.append("holds a line of the doc's own layout, not email copy: %r (a grey (section)/(note) "
                        "marker was probably deleted)" % line.strip())

    if field == "body" and not text.strip():
        errs.append("the body is empty")
    if field == "subject":
        if old.strip() == "" and text:
            errs.append("this step has no subject of its own so it stays in the first email's thread; "
                        "a subject here would start a new thread")
        if old.strip() and not text:
            errs.append("the subject is empty; only a follow-up in the same thread goes without one")
    for ch, name in sorted(DASH_CHARS.items()):
        if ch in text:
            errs.append("contains a dash (%s %s)" % (name, ch))
    if "--" in text:
        errs.append("contains '--' used as a dash")
    for ch, name in sorted(EXCLAMATION_CHARS.items()):
        if ch in text:
            errs.append("contains an %s (%s)" % (name, ch))
    ai = L.AI_RE.search(text)
    if ai:
        errs.append("mentions AI or automation (%r)" % ai.group(0))
    try:
        tags = L.find_tags(text)
    except L.TagError as exc:
        errs.append("unbalanced {{ }}: %s" % exc)
        return errs, warns
    rest = text
    for s, e, _inner in reversed(tags):
        rest = rest[:s] + rest[e:]
    singles = SINGLE_BRACE_RE.findall(rest)
    if singles:
        errs.append("single-brace placeholder %s: Instantly only fills {{name}}, e.g. {{firstName}}; "
                    "a lead would see the braces" % ", ".join(sorted(set(singles))))
    elif "{" in rest or "}" in rest:
        errs.append("a stray { or } outside a {{name}} tag")
    squares = SQUARE_PLACEHOLDER_RE.findall(rest)
    if squares:
        warns.append("square-bracket text %s: if it is meant as a placeholder, Instantly will not fill it"
                     % ", ".join(sorted(set(squares))))
    for _s, _e, inner in tags:
        head = inner.split("|", 1)[0]
        if head.strip().upper() != "RANDOM" and inner != inner.strip():
            warns.append("{{%s}} has spaces inside the braces; write {{%s}}" % (inner, inner.strip()))
    # spintax: a variable inside a spin option ships a literal tag
    # (copy_validator rule 1); each spin needs 2+ distinct, non-empty options.
    for found in variables_inside_spins(text):
        errs.append("merge variable inside a spin option: %s (Instantly would send the tag literally)" % found)
    for raw, options in L.iter_spins(text):
        if len(options) < 2:
            errs.append("spin needs at least two options: %s" % raw[:60])
        if any(o == "" for o in options):
            errs.append("spin has an empty option: %s" % raw[:60])
        if len(set(options)) != len(options):
            errs.append("spin repeats an option: %s" % raw[:60])
    names = L.merge_variables(text)
    for name in sorted(names):
        if not L.VAR_NAME_RE.match(name):
            errs.append("malformed tag {{%s}}" % name)
        elif known_vars is not None and name not in known_vars:
            errs.append("{{%s}} is not a variable this campaign has (%s)" % (name, ", ".join(sorted(known_vars))))
    try:
        removed = sorted(L.merge_variables(old_text) - names)
    except L.TagError:
        removed = []
    for name in removed:
        warns.append("{{%s}} was in the old text and is not in the new one" % name)

    # offers.md (fail closed: no offer sheet or no offer type means no check,
    # so refuse)
    if not offers_md or not offers_md.strip():
        errs.append("config/offers.md could not be read, so dollar figures and promises cannot be checked")
    elif offer not in ("reactivation", "outbound"):
        errs.append("config/ids.json gives campaign %s no offer type (reactivation|outbound), so its "
                    "figures cannot be checked" % campaign_key)
    else:
        money, periods = L.allowed_offer_numbers(campaign_key, offer, offers_md)
        for amount in sorted(L.money_values(text) - L.money_values(old_text) - money):
            errs.append("new dollar figure %s is not in this campaign's config/offers.md row or proof line"
                        % L._fmt_money(amount))
        old_keys = set(k for _p, k, _e in time_windows(old_text))
        for phrase, key, exempt in time_windows(text):
            if not exempt and key not in old_keys and key not in periods:
                errs.append("new time window '%ss' (%r) is not in this campaign's config/offers.md row or proof "
                            "line; a changed guarantee or case-study window is a changed promise" % (key, phrase))
        if offer == "reactivation":
            g = L.GUARANTEE_RE.search(text)
            if g and not L.GUARANTEE_RE.search(old_text):
                errs.append("guarantee language %r on a reactivation offer, which has no guarantee in "
                            "config/offers.md" % g.group(0))
    return _unique(errs), _unique(warns)


def _unique(items: List[str]) -> List[str]:
    seen = set()  # type: Set[str]
    return [i for i in items if not (i in seen or seen.add(i))]


# ------------------------------------------------------------------ sequences
def steps_of(sequences: Any) -> List[Dict[str, Any]]:
    try:
        return (sequences or [{}])[0].get("steps") or []
    except (AttributeError, IndexError, TypeError):
        return []


def manifest_baseline(blocks: List[Dict[str, Any]], snapshot_campaign: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The copy the doc was built from, as a sequences list: each step's type
    from the snapshot, its delay and delay_unit from the manifest, and every
    variant's subject/body from the manifest's raw_subject/raw_html. Raises
    BuildError when the manifest does not cover every snapshot step and
    variant (then "unchanged" would not be checkable)."""
    snap_steps = steps_of(snapshot_campaign.get("sequences"))
    by = dict(((b["step"], b.get("variant_index", 0), b["field"]), b) for b in blocks)
    steps_in_manifest = sorted(set(b["step"] for b in blocks))
    if steps_in_manifest != list(range(1, len(snap_steps) + 1)):
        raise BuildError("the manifest has steps %s, the snapshot %d steps" % (steps_in_manifest, len(snap_steps)))
    out_steps = []
    for si, st in enumerate(snap_steps):
        variants = []
        body0 = None
        for vi in range(len(st.get("variants") or [])):
            body = by.get((si + 1, vi, "body"))
            subj = by.get((si + 1, vi, "subject"))
            if body is None or subj is None:
                raise BuildError("step %d variant %d is in the snapshot but not in the manifest" % (si + 1, vi))
            body0 = body0 or body
            variants.append({"subject": subj.get("raw_subject"), "body": body.get("raw_html")})
        extra = [b for b in blocks if b["step"] == si + 1 and b.get("variant_index", 0) >= len(variants)]
        if extra:
            raise BuildError("%s: not in the snapshot" % extra[0]["tag"])
        out_steps.append({"type": st.get("type"),
                          "delay": (body0 or {}).get("delay", st.get("delay")),
                          "delay_unit": (body0 or {}).get("delay_unit", st.get("delay_unit")),
                          "variants": variants})
    return [{"steps": out_steps}]


def apply_changes(sequences: List[Dict[str, Any]], changes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """A deep copy of ``sequences`` with ONLY each change's variant field set to
    its ``value``. Every other step, variant and key is left exactly as it was
    (live-only keys such as v_disabled or pre_delay_unit included)."""
    out = copy.deepcopy(sequences)
    steps = steps_of(out)
    for ch in changes:
        step, vi, field = ch.get("step"), ch.get("variant_index"), ch.get("field")
        if field not in FIELDS:
            raise BuildError("%s: field %r is not body or subject" % (ch.get("tag"), field))
        if not isinstance(step, int) or not isinstance(vi, int) or isinstance(step, bool) or isinstance(vi, bool):
            raise BuildError("%s: step and variant_index must be integers" % ch.get("tag"))
        if step < 1 or step > len(steps) or vi < 0 or vi >= len(steps[step - 1].get("variants") or []):
            raise BuildError("%s: step %r variant %r does not exist" % (ch.get("tag"), step, vi))
        if not isinstance(ch.get("value"), str):
            raise BuildError("%s: the staged value is not text" % ch.get("tag"))
        steps[step - 1]["variants"][vi][field] = ch["value"]
    return out


def drift(live_sequences: Any, baseline_sequences: Any, changes: List[Dict[str, Any]]) -> List[str]:
    """Where live has moved away from the baseline the doc was built from.

    Checked: the step count, each step's type, delay and delay_unit, each
    step's variant count, and every variant's subject and body. A variant field
    the change-set edits may hold either the baseline value (not applied yet)
    or the staged value (already applied); anything else is drift. Other keys
    (v_disabled, pre_delay_unit, keys Instantly adds) are not compared: the
    PATCH is built from live, so they are carried over untouched.
    Empty list = no drift."""
    out = []  # type: List[str]
    live_steps = steps_of(live_sequences)
    base_steps = steps_of(baseline_sequences)
    if len(live_steps) != len(base_steps):
        out.append("live has %d steps, the doc was built from %d" % (len(live_steps), len(base_steps)))
        return out
    staged = dict(((c["step"], c["variant_index"], c["field"]), c["value"]) for c in changes)
    for si, (ls, bs) in enumerate(zip(live_steps, base_steps)):
        where = "step%d" % (si + 1)
        for key in ("type", "delay", "delay_unit"):
            if ls.get(key) != bs.get(key):
                out.append("%s %s: live %r, doc baseline %r" % (where, key, ls.get(key), bs.get(key)))
        lv, bv = ls.get("variants") or [], bs.get("variants") or []
        if len(lv) != len(bv):
            out.append("%s: live has %d variants, the doc was built from %d" % (where, len(lv), len(bv)))
            continue
        for vi, (a, b) in enumerate(zip(lv, bv)):
            for field in FIELDS:
                have, base = a.get(field), b.get(field)
                ok = [base]
                if (si + 1, vi, field) in staged:
                    ok.append(staged[(si + 1, vi, field)])
                if have not in ok:
                    line = "%s variant %d %s: live differs from the doc baseline" % (where, vi, field)
                    if field == "body":
                        line += "\n" + "\n".join("    " + d for d in difflib.unified_diff(
                            L.html_to_text(base or "").split("\n"), L.html_to_text(have or "").split("\n"),
                            fromfile="doc baseline", tofile="live", lineterm="", n=1))
                    else:
                        line += ": live %r, baseline %r" % (have, base)
                    out.append(line)
    return out


def text_diff(live_sequences: Any, target_sequences: Any, campaign_key: str) -> str:
    """Unified plain-text diff live -> target, per variant (phase0's)."""
    return L.sequence_diff({"sequences": live_sequences}, {"sequences": target_sequences}, campaign_key)
