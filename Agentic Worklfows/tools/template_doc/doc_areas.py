"""The doc as plain text, and every line of it that is NOT a block body.

parse_doc.py returns only block bodies. Everything else Lorenzo can see or type
in (the top section, headings and variant labels, "(note)" lines such as the
fallback subjects, "(section)" lines, and text typed between a section line
and the next tag) is an "area" line here. build.py stores the area lines of
the doc it builds, and record_doc_approvals.py compares the export's area
lines with them, so nothing outside a block body can change unseen.

Area keys:
    "top"        lines before the first tag (the doc's top section)
    <tag>        a label or heading tag line and the (note) lines inside its block
    "gap:<tag>"  (section) lines and anything typed while no block is open,
                 keyed by the next tag ("gap:END" after the last one)

Lines are compared after canon(): tag, note and section markers written the
same way, then diff_doc.norm (curly quotes, non-breaking spaces, runs of
spaces). Blank lines are not area lines.

html_to_text() is selftest.py's Drive rendering, copied here because
selftest.py runs its checks at import; tests/test_record_doc_approvals.py
checks the two copies give the same text.
"""
import hashlib
import io
import json
import re
from collections import OrderedDict
from html.parser import HTMLParser

from diff_doc import norm
from parse_doc import NOTE_RE, SECTION_RE, TAG_RE, split_lines

BUILD_TAG = "X-BUILD"
FP_LEN = 16
FP_RE = re.compile(r"(?<![0-9a-f])([0-9a-f]{%d})(?![0-9a-f])" % FP_LEN)
FP_MASK = "<fingerprint>"
FP_PLACEHOLDER = "f" * FP_LEN

# ------------------------------------------------ selftest.py's rendering
BLOCK = {"h1", "h2", "h3", "h4", "h5", "h6", "p", "div", "li", "tr", "td", "th", "table", "title"}
SKIP = {"head", "title", "style", "script"}


class GoogleText(HTMLParser):
    def __init__(self):
        HTMLParser.__init__(self, convert_charrefs=True)
        self.paras = []
        self.cur = None
        self.skip = 0

    def flush(self):
        if self.cur is not None:
            self.paras.append(self.cur)
        self.cur = None

    def handle_starttag(self, tag, attrs):
        if tag in SKIP:
            self.skip += 1
            return
        if tag in BLOCK:
            self.flush()
        elif tag == "br":
            self.cur = "" if self.cur is None else self.cur + "\n"

    def handle_endtag(self, tag):
        if tag in SKIP:
            self.skip -= 1
            return
        if tag in BLOCK:
            self.flush()

    def handle_data(self, d):
        if self.skip:
            return
        d = re.sub(r"[ \t\r\n]+", " ", d)
        if self.cur is None:
            if not d.strip():
                return
            self.cur = d
        else:
            self.cur += d

    def text(self):
        self.flush()
        return "\n".join(p.strip(" ") if p.strip() else "" for p in self.paras)


def html_string_to_text(html_text):
    g = GoogleText()
    g.feed(html_text)
    return g.text()


def html_to_text(path):
    with io.open(path, encoding="utf-8") as fh:
        return html_string_to_text(fh.read())


# ------------------------------------------------------------ area lines
_NOTE_MARK = re.compile(r"\(\s*note\s*\)", re.IGNORECASE)
_SECTION_MARK = re.compile(r"\(\s*section\s*\)", re.IGNORECASE)


def canon(line, mask_fingerprint=False):
    t = TAG_RE.sub(lambda m: "(tag: %s)" % m.group(1), line)
    t = _NOTE_MARK.sub("(note)", t)
    t = _SECTION_MARK.sub("(section)", t)
    if mask_fingerprint:
        t = FP_RE.sub(FP_MASK, t)
    return norm(t)


def layout(text):
    """[(kind, key, line)] for every non-blank line, in order.
    kind: top, tag, subject, body, note, gap. key: see the module doc."""
    out = []
    cur = None
    seen_tag = False
    for line in split_lines(text):
        tags = list(TAG_RE.finditer(line))
        if tags:
            tag = tags[-1].group(1)
            seen_tag = True
            if tag.lower().endswith("/subject"):
                out.append(["subject", tag, line])
                continue
            out.append(["tag", tag, line])
            cur = tag
            continue
        if not line.strip():
            continue
        if not seen_tag:
            out.append(["top", "top", line])
        elif SECTION_RE.search(line):
            cur = None
            out.append(["gap", None, line])
        elif NOTE_RE.search(line):
            out.append(["note", cur, line] if cur is not None else ["gap", None, line])
        elif cur is not None:
            out.append(["body", cur, line])
        else:
            out.append(["gap", None, line])
    nxt = "END"
    for item in reversed(out):
        if item[0] in ("tag", "subject"):
            nxt = item[1]
        elif item[0] == "gap":
            item[1] = "gap:" + nxt
    return [tuple(i) for i in out]


def area_pairs(text):
    """[[key, canon line]] for every area line, in doc order. The build line's
    fingerprint is masked (the fingerprint is checked on its own)."""
    pairs = []
    for kind, key, line in layout(text):
        if kind in ("top", "tag", "note", "gap"):
            is_build = kind == "tag" and key == BUILD_TAG
            pairs.append([key, canon(line, mask_fingerprint=is_build)])
    return pairs


def areas(pairs):
    """OrderedDict key -> [canon lines] from area pairs."""
    out = OrderedDict()
    for key, line in pairs:
        out.setdefault(key, []).append(line)
    return out


def read_fingerprint(text):
    """(fingerprint or None, problem or None) from the doc's build line."""
    found = []
    for kind, key, line in layout(text):
        if kind == "tag" and key == BUILD_TAG:
            found.append(FP_RE.findall(TAG_RE.sub("", line)))
    if not found:
        return None, None
    if len(found) > 1:
        return None, "the build line appears %d times" % len(found)
    if len(found[0]) != 1:
        return None, "the build line does not carry exactly one fingerprint"
    return found[0][0], None


def fingerprint(blocks, visible):
    """The build fingerprint: every block's tag, text and hash, and every
    area line (build line masked)."""
    payload = {"blocks": [[b.get("tag"), b.get("text"), b.get("sha256")] for b in blocks],
               "visible": [[k, l] for k, l in visible]}
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:FP_LEN]
