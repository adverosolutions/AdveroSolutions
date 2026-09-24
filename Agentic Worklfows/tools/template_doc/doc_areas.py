"""The doc as plain text: every line of it that is NOT a block body, and every
template read back out of it.

parse_doc.py returns only block bodies. Everything else Lorenzo can see or type
in (the top section, headings and variant labels, "(note)" lines such as the
fallback subjects and the lines a version replaces or leaves out, "(section)"
lines, and text typed between a section line and the next tag) is an "area"
line here. build.py stores the area lines of the doc it builds, and
record_doc_approvals.py compares the export's area lines with them, so nothing
outside a block body can change unseen.

Area keys:
    "top"        lines before the first tag (the doc's top section)
    <tag>        a label or heading tag line and the (note) lines inside its block
    "gap:<tag>"  (section) lines and anything typed while no block is open,
                 keyed by the next tag ("gap:END" after the last one)

Lines are compared after canon(): tag, note and section markers written the
same way, then diff_doc.norm (curly quotes, non-breaking spaces, runs of
spaces). Blank lines are not area lines. A (note) line inside a block also
records how many body lines of that block are above it (" @n"): in a
version's block the notes say which lines the body lines below them replace,
so a note moved up or down within its block is a change too.

DocReader rebuilds every part of every template's hashed review text (the
main text, the subject line and its fallbacks, each version, the time
formats) from the doc's plain text alone, the way doc_rules says the doc
writes them. build.py runs it on every doc it builds and refuses to write a
doc that does not read back exactly, so a template's hashed text can never
differ from what its doc shows.

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

import doc_rules
from diff_doc import norm
from parse_doc import NOTE_RE, SECTION_RE, SUBJECT_PREFIX_RE, TAG_RE, split_lines

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
    fingerprint is masked (the fingerprint is checked on its own). A note
    inside a block ends with " @n", n being the number of body lines of that
    block above it."""
    pairs = []
    body_seen = {}
    for kind, key, line in layout(text):
        if kind == "body":
            body_seen[key] = body_seen.get(key, 0) + 1
        elif kind in ("top", "tag", "note", "gap"):
            is_build = kind == "tag" and key == BUILD_TAG
            c = canon(line, mask_fingerprint=is_build)
            if kind == "note":
                c = "%s @%d" % (c, body_seen.get(key, 0))
            pairs.append([key, c])
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


# ------------------------------------------------ templates read back from the doc
class DocError(ValueError):
    """The doc's text does not show a part of a template in the form
    doc_rules describes."""


def _strip_blank(lines):
    lines = list(lines)
    while lines and not lines[-1].strip():
        lines.pop()
    while lines and not lines[0].strip():
        lines.pop(0)
    return lines


def _find_run(out, cur, kind, note):
    """(first, last) index of the consecutive non-blank lines of out, at or
    after cur, that the note quotes; the first such run."""
    for a in range(cur, len(out)):
        if not out[a].strip():
            continue
        quoted = []
        for b in range(a, len(out)):
            if not out[b].strip():
                continue
            quoted.append(out[b])
            rendered = doc_rules.change_note(kind, quoted)
            if rendered == note:
                return a, b
            if len(rendered) > len(note):
                break
    raise DocError("%r does not quote lines of the text at or after line %d" % (note, cur + 1))


def _find_anchor(out, cur, kind, note):
    for k in range(cur, len(out)):
        if out[k].strip() and doc_rules.change_note(kind, [out[k]]) == note:
            return k
    raise DocError("%r does not quote a line of the text at or after line %d" % (note, cur + 1))


def apply_changes(lines, changes):
    """The lines with the changes applied, in order. changes: [(kind, note,
    new lines)] as doc_rules describes them. Each change is looked for at or
    after the end of the one before it."""
    out = list(lines)
    cur = 0
    for kind, note, new in changes:
        new = list(new)
        if kind in ("start", "start_para"):
            if cur:
                raise DocError("%r is not the first change" % note)
            out[0:0] = new + ([""] if kind == "start_para" else [])
            cur = len(new) + (1 if kind == "start_para" else 0)
        elif kind in doc_rules.QUOTING:
            a, b = _find_run(out, cur, kind, note)
            repl = new if kind == "instead" else []
            out[a:b + 1] = repl
            cur = a + len(repl)
        elif kind in doc_rules.ANCHORED:
            k = _find_anchor(out, cur, kind, note)
            if kind == "before":
                out[k:k] = new
                cur = k + len(new)
            else:
                add = ([""] if kind == "after_para" else []) + new
                out[k + 1:k + 1] = add
                cur = k + 1 + len(add)
        else:
            raise DocError("unknown change %r" % (kind,))
    return out


_GREETING_RE = re.compile(r"If we don't have their first name, '([^']*)' becomes '([^']*)'\.")
_COMPANY_RE = re.compile(r"If we don't have their company name, \{company\} becomes '([^']*)' \('([^']*)' in the "
                         r"Day ([0-9]+(?:, [0-9]+)*(?: and [0-9]+)?) follow-ups\)\.")
_REFERRAL_RE = re.compile(r"In a referral reply with no name, (\{[A-Za-z_]+\}) becomes '([^']*)' and "
                          r"(\{[A-Za-z_]+\}) becomes '([^']*)'\.")


class DocReader(object):
    """Every template in the doc, read back from its plain text alone.

        r = DocReader(text)
        r.main(tid)          the main text, with the Subject line when it is part of it
        r.part(tid, name)    one part of its review text: "subject", "value_formats"
                             or a version name ("no_slots", "missing_lead_data", ...)

    Lines come back normalised as the hash normalises them (doc_rules.norm_lines),
    except main(), which is the doc's lines as they are. Raises DocError when
    the doc does not show the part in a form doc_rules describes.
    """

    def __init__(self, text):
        self.top = []
        self.items = OrderedDict()     # tag -> [(kind, value)]: note, body, subject
        self.labels = OrderedDict()    # tag -> its heading or label text
        self.subjects = OrderedDict()  # template id -> the Subject line's text
        self.duplicates = []
        cur = None
        seen = False
        for line in split_lines(text):
            tags = list(TAG_RE.finditer(line))
            if tags:
                seen = True
                tag = tags[-1].group(1)
                rest = TAG_RE.sub(u"", line)
                if tag.lower().endswith("/subject"):
                    tid = tag[:-len("/subject")]
                    if tid in self.subjects:
                        self.duplicates.append(tag)
                    self.subjects[tid] = SUBJECT_PREFIX_RE.sub(u"", rest.strip(), count=1).rstrip()
                    if cur is not None:
                        self.items[cur].append(("subject", tid))
                    continue
                if tag in self.items:
                    self.duplicates.append(tag)
                cur = tag
                self.items[cur] = []
                self.labels[cur] = rest.strip()
                continue
            if not seen:
                self.top.append(line)
            elif SECTION_RE.search(line):
                cur = None
            elif NOTE_RE.search(line):
                if cur is not None:
                    self.items[cur].append(("note", NOTE_RE.sub(u"", line).strip()))
            elif cur is not None:
                self.items[cur].append(("body", line.rstrip()))

    # ------------------------------------------------------------ plumbing
    def _block(self, tag):
        if self.duplicates:
            raise DocError("duplicate tags in the doc: %s" % ", ".join(sorted(set(self.duplicates))))
        if tag not in self.items:
            raise DocError("%s is not in the doc" % tag)
        return self.items[tag]

    def body(self, tag):
        return _strip_blank([v for k, v in self._block(tag) if k == "body"])

    def notes(self, tag):
        return [v for k, v in self._block(tag) if k == "note"]

    def template_ids(self):
        return [t for t in self.items if "/" not in t and doc_rules.section_of(t)]

    def _subject_fallbacks(self, tid):
        """The fallback lines of a subject variant (the note right after the
        Subject line), or None when the Subject line is part of the main text."""
        items = self._block(tid)
        for i, (k, v) in enumerate(items):
            if k == "subject" and v == tid:
                if i + 1 < len(items) and items[i + 1][0] == "note":
                    return doc_rules.read_subject_note(items[i + 1][1])
                return None
        return None

    def _pin(self, tid):
        pins = [m for m in (doc_rules.PIN_RE.match(n) for n in self.notes(tid)) if m]
        if len(pins) > 1:
            raise DocError("%s has more than one spliced-line note" % tid)
        return (pins[0].group(1), pins[0].group(2)) if pins else None

    def _resplice(self, tid, lines):
        pin = self._pin(tid)
        return [l.replace(pin[0], pin[1]) for l in lines] if pin else list(lines)

    def _formats_tag(self, tid):
        versions = [m for m in (doc_rules.VF_VERSION_RE.match(n) for n in self.notes(tid)) if m]
        if len(versions) > 1:
            raise DocError("%s names more than one time formats version" % tid)
        if versions:
            return "formats.%s" % versions[0].group(1)
        found = [t for t in self.items if t.startswith("formats.")]
        if len(found) != 1:
            raise DocError("%s does not say which of %d time formats blocks it uses" % (tid, len(found)))
        return found[0]

    def _missing_rules(self):
        top = u" ".join(l.strip() for l in self.top if l.strip())
        found = []
        for rx in (_GREETING_RE, _COMPANY_RE, _REFERRAL_RE):
            ms = list(rx.finditer(top))
            if len(ms) != 1:
                raise DocError("the top section does not say once how missing lead data is written")
            found.append(ms[0])
        g, c, r = found
        days = re.split(r", | and ", c.group(3))
        team = []
        for d in days:
            hits = [t for t in self.template_ids() if self.labels.get(t) == "Day %s follow-up" % d]
            if len(hits) != 1:
                raise DocError("the top section names Day %s, which is not one heading in the doc" % d)
            team.append(hits[0])
        return {"greeting": (g.group(1), g.group(2)), "company": c.group(1), "company_team": c.group(2),
                "team": team, "referrals": ((r.group(1), r.group(2)), (r.group(3), r.group(4)))}

    def changes(self, tag):
        """(special note or None, [(kind, note, new lines)]) of a version's
        block. special is doc_rules.SAME_AS_MAIN, doc_rules.WHOLE_NOTE (then
        the one "change" holds the version's lines) or a COMBOS note."""
        specials = [doc_rules.SAME_AS_MAIN, doc_rules.WHOLE_NOTE] + [n for _, n in doc_rules.COMBOS.values()]
        out, special, whole = [], None, []
        for k, v in self._block(tag):
            if k == "note":
                kind = doc_rules.change_kind(v)
                if kind is not None and special is None:
                    out.append((kind, v, []))
                elif v in specials and special is None and not out:
                    special = v
                elif out or special is not None:
                    raise DocError("an unexpected note among the changes of %s: %r" % (tag, v))
            elif k == "body":
                if out and special is None:
                    out[-1][2].append(v)
                elif special == doc_rules.WHOLE_NOTE:
                    whole.append(v)
                elif v.strip():
                    raise DocError("%s has text that no change note introduces" % tag)
            else:
                raise DocError("%s holds a Subject line" % tag)
        if special == doc_rules.WHOLE_NOTE:
            whole = _strip_blank(whole)
            if not whole:
                raise DocError("%s: %r has no lines after it" % (tag, special))
            return special, [("whole", special, whole)]
        res = []
        for kind, note, new in out:
            new = _strip_blank(new)
            if (kind == "leaves") != (not new):
                raise DocError("%s: %r %s" % (tag, note, "has lines after it" if new else "has no lines after it"))
            res.append((kind, note, new))
        if special is None and not res:
            raise DocError("%s shows no change" % tag)
        return special, res

    # ----------------------------------------------------------- the parts
    def main(self, tid):
        body = self.body(tid)
        if tid in self.subjects and self._subject_fallbacks(tid) is None:
            return [doc_rules.SUBJECT_PREFIX + self.subjects[tid], u""] + body
        return body

    def part(self, tid, name):
        if name == "subject":
            fb = self._subject_fallbacks(tid)
            if tid not in self.subjects or fb is None:
                raise DocError("%s shows no subject line with its fallbacks" % tid)
            return doc_rules.norm_lines([doc_rules.SUBJECT_PREFIX + self.subjects[tid]] + fb)
        if name == "value_formats":
            return doc_rules.norm_lines(self.body(self._formats_tag(tid)))
        tag = "%s/%s" % (tid, name)
        if tag in self.items:
            return self._version(tid, tag, name)
        if name == "missing_lead_data":
            rules = self._missing_rules()
            company = rules["company_team"] if tid in rules["team"] else rules["company"]
            lines = doc_rules.fill_missing(self._resplice(tid, self.main(tid)), rules["greeting"], company,
                                           rules["referrals"])
            return doc_rules.norm_lines(lines)
        raise DocError("%s is not in the doc" % tag)

    def _version(self, tid, tag, name):
        special, changes = self.changes(tag)
        lines = self.main(tid)
        if special == doc_rules.SAME_AS_MAIN:
            pass
        elif special == doc_rules.WHOLE_NOTE:
            lines = changes[0][2]
        elif special is not None:
            parts, note = doc_rules.COMBOS.get(name, ((), None))
            if special != note:
                raise DocError("%s: %r is not the note for this version" % (tag, special))
            for p in parts:
                sp, ch = self.changes("%s/%s" % (tid, p))
                if sp not in (None, doc_rules.SAME_AS_MAIN):
                    raise DocError("%s: %s/%s is not shown as changes" % (tag, tid, p))
                lines = apply_changes(lines, ch)
        else:
            lines = apply_changes(lines, changes)
        return doc_rules.norm_lines(self._resplice(tid, lines))
