"""Read a plain-text export of the Google Doc and return {tag: text}.

Input is what Drive's text/plain export gives: one line per heading or
paragraph, the grey tags inline. Python 3.9, standard library only.

Rules (the same ones build.py writes the doc for):
- A line with "(tag: X)" starts block X.
  * A tag ending in "/subject" is a one-line block: the text outside the tag,
    minus a leading "Subject:". It does not end the block that was open, so a
    Subject line between a heading and its body leaves the body with the
    heading's tag.
  * Any other tag line is a label (heading or "If there are no free times:").
    Its block is the lines after it, up to the next tag line or "(section)" line.
- A line ending in "(section)" ends the open block and is skipped.
- A line ending in "(note)" is skipped and does not end the open block.
- Anything before the first tag (the doc's top section) is ignored.

Returned text: lines right-stripped, blank lines at both ends dropped, inner
blank lines kept as they came. Nothing else is changed (no quote or space
normalisation); diff_doc.norm does that for comparison only.

    python3 parse_doc.py export.txt            # prints JSON {tag: text}
"""
import json
import re
import sys
from collections import OrderedDict

TAG_RE = re.compile(r"\(\s*tag\s*:\s*([^()\s]+)\s*\)", re.IGNORECASE)
SECTION_RE = re.compile(r"\(\s*section\s*\)\s*$", re.IGNORECASE)
NOTE_RE = re.compile(r"\(\s*note\s*\)\s*$", re.IGNORECASE)
SUBJECT_PREFIX_RE = re.compile(r"^\s*subject\s*:\s?", re.IGNORECASE)
ZERO_WIDTH = dict.fromkeys(map(ord, u"﻿​‌‍⁠"), None)
LINE_BREAKS = (u"\r\n", u"\r", u"\u000b", u" ", u" ", u"\u000c")


def split_lines(text):
    text = text.translate(ZERO_WIDTH)
    for br in LINE_BREAKS:
        text = text.replace(br, u"\n")
    return text.split(u"\n")


def _finish(lines):
    lines = [l.rstrip() for l in lines]
    while lines and not lines[-1].strip():
        lines.pop()
    while lines and not lines[0].strip():
        lines.pop(0)
    return u"\n".join(lines)


def parse_with_info(text):
    """{"blocks": {tag: text}, "duplicates": [tag, ...], "order": [tag, ...]}"""
    raw = OrderedDict()
    duplicates = []
    order = []
    cur = None
    for line in split_lines(text):
        tags = list(TAG_RE.finditer(line))
        if tags:
            tag = tags[-1].group(1)
            rest = TAG_RE.sub(u"", line)
            if tag in raw:
                duplicates.append(tag)
                tag_key = u"%s#dup%d" % (tag, duplicates.count(tag))
            else:
                tag_key = tag
            order.append(tag)
            if tag.lower().endswith(u"/subject"):
                raw[tag_key] = [SUBJECT_PREFIX_RE.sub(u"", rest.strip(), count=1)]
                continue  # the open block stays open
            raw[tag_key] = []
            cur = tag_key
            continue
        if SECTION_RE.search(line):
            cur = None
            continue
        if NOTE_RE.search(line):
            continue
        if cur is not None:
            raw[cur].append(line)
    blocks = OrderedDict((k, _finish(v)) for k, v in raw.items() if u"#dup" not in k)
    return {"blocks": blocks, "duplicates": duplicates, "order": order,
            "duplicate_texts": OrderedDict((k, _finish(v)) for k, v in raw.items() if u"#dup" in k)}


def parse(text):
    """{tag: text}"""
    return parse_with_info(text)["blocks"]


def parse_file(path):
    with open(path, "rb") as fh:
        data = fh.read()
    return parse(data.decode("utf-8-sig"))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: parse_doc.py <plain-text export>")
    print(json.dumps(parse_file(sys.argv[1]), indent=1, ensure_ascii=False))
