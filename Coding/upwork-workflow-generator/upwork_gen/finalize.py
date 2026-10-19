"""Fill a job's proposal placeholders, copy it, and log the application.

    python3 -m upwork_gen.finalize <job_dir> --loom <url> --runtime <minutes> \\
        --start "<text>" [--draft "<text>"] [--name <FirstName>] [--variant <label>] \\
        [--replace-loom] [--relog] [--no-log] [--no-copy] [--csv <path>]

Replaces `https://www.loom.com/share/[LOOMURL]`, `[N]-min`, `[START]` and
`[DRAFT]`; `--name` turns "Hey [greeting]" (or "Hey there") into "Hey <Name>"
(stripped; a blank --name is no name and leaves the greeting alone). The preview is
recounted and printed, and a count outside 133-150 is flagged, never
auto-edited. Refuses (exit 2, nothing written) if `[LOOMURL]`, `[START]` or
`[greeting]` would remain.

--loom is stored as https://www.loom.com/share/<video id>: a trailing slash,
`?sid=...` or `#t=...` from the share dialog is dropped.

Safe to run twice. When `[LOOMURL]` is already filled it refuses (exit 2)
unless the proposal's Loom is the same video as --loom (compared on the video
id alone), or --replace-loom is given (which swaps the whole link). Either
way, when the preview still has the `[N]-min` placeholder, --runtime fills
only the placeholder and never touches a real `<n>-min` token (one typed by
hand stays as it is, and is named as left). Without the placeholder
--runtime updates the preview's `<n>-min` token when it has exactly one
(with several or none it warns and leaves the preview as it is). A job_url already in
proposals.csv is not logged again unless --relog is given; after
--replace-loom its existing row(s) get the new loom_url and
opener_visible_chars in place instead, and after any other re-run that
changes the preview count (a runtime change, a --name) the new
opener_visible_chars. That edit must reach exactly the
rows csv reads for the job_url: otherwise it refuses (exit 2) before writing
anything. The log row (spec.json, jd.txt) is also built before anything is
written. Logging needs a `url:` line in jd.txt (otherwise pass --no-log).
"""

from __future__ import annotations

import argparse
import csv
import datetime
import io
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from typing import Dict, List, Optional, Tuple

from . import apply_meta
from .spec import WorkflowSpec, slugify
from .verify_job import (
    LOOM_MARK,
    LOOM_PLACEHOLDER,
    LOOM_SHARE,
    LOOM_TOKEN,
    PREVIEW_MAX,
    PREVIEW_MIN,
    UP_ROOT,
    jd_fields,
    platform_label,
    preview_length,
    read_text,
)

PROPOSALS_CSV = os.path.join(UP_ROOT, "proposals.csv")
CSV_HEADER = [
    "applied_at", "job_title", "job_url", "job_created_utc", "age_hours_at_apply",
    "platform", "build_slug", "node_count", "loom_url", "opener_variant",
    "opener_visible_chars", "connects", "boosted", "viewed", "replied",
    "interviewed", "hired", "notes",
]
REQUIRED_GONE = ("[LOOMURL]", "[START]", "[greeting]")
GREETING_PLACEHOLDER = "Hey [greeting]"
# What --loom may look like: the share link, optionally with the trailing
# slash, query string and fragment the share dialog sometimes adds.
_LOOM_ARG = re.compile(r"^https://www\.loom\.com/share/([A-Za-z0-9]+)/?(?:\?[^\s#]*)?(?:#\S*)?$")
_RUNTIME_TOKEN = re.compile(r"\b\d+-min\b")
_LINE_BREAK = re.compile(r"\r\n|\r|\n")


def fill(text: str, loom: str, runtime: int, start: str, draft: Optional[str] = None,
         name: Optional[str] = None) -> Tuple[str, List[str]]:
    """Return (filled text, placeholders that still remain). `name` is
    stripped; a blank one leaves "Hey there" or "Hey [greeting]" as it is."""
    name = normalize_name(name)
    out = text.replace(LOOM_PLACEHOLDER, loom)
    out = out.replace("[N]-min", "{}-min".format(int(runtime)))
    out = out.replace("[START]", start)
    if draft is not None:
        out = out.replace("[DRAFT]", draft)
    if name:
        if GREETING_PLACEHOLDER in out:
            out = out.replace(GREETING_PLACEHOLDER, "Hey {}".format(name), 1)
        else:
            out = out.replace("Hey there", "Hey {}".format(name), 1)
    remaining = [p for p in ("[LOOMURL]", "[START]", "[greeting]", "[DRAFT]", "[N]")
                 if p in out]
    return out, remaining


def normalize_name(name: Optional[str]) -> Optional[str]:
    """--name stripped, or None when it is missing or blank (no name)."""
    name = (name or "").strip()
    return name or None


def normalize_loom(url: str) -> Optional[str]:
    """`https://www.loom.com/share/<id>` for a --loom value, or None when it is
    not a Loom share link."""
    match = _LOOM_ARG.match(url.strip())
    return LOOM_SHARE + match.group(1) if match else None


def loom_id(url: str) -> Optional[str]:
    """The video id of a Loom share link (a --loom value or a proposal token)."""
    match = LOOM_TOKEN.match(url.strip())
    return match.group(1) if match else None


def existing_loom(text: str) -> Optional[str]:
    """The first real Loom share link already in the proposal, whole: the
    video id plus any `/`, `?sid=...` or other text glued to it."""
    match = LOOM_TOKEN.search(text)
    return match.group(0) if match else None


def set_loom(text: str, video_id: str, loom: str) -> str:
    """Every whole link token for `video_id` becomes `loom`."""
    return LOOM_TOKEN.sub(lambda m: loom if m.group(1) == video_id else m.group(0), text)


def _preview_end(text: str) -> int:
    """Where the Upwork preview ends: the first `https://www.loom` after any
    leading whitespace, or -1 when there is none."""
    return text.find(LOOM_MARK, len(text) - len(text.lstrip()))


def runtime_tokens(text: str) -> List[str]:
    """The `<n>-min` tokens in the preview (the Loom runtime it states)."""
    end = _preview_end(text)
    return _RUNTIME_TOKEN.findall(text[:end]) if end >= 0 else []


def set_runtime(text: str, runtime: int) -> str:
    """Every `<n>-min` token in the preview says `runtime`. The body is left
    alone: a "30-min call" further down is not the Loom runtime."""
    end = _preview_end(text)
    if end < 0:
        return text
    return _RUNTIME_TOKEN.sub("{}-min".format(int(runtime)), text[:end]) + text[end:]


def runtime_placeholder(text: str) -> bool:
    """Whether the preview still has the `[N]-min` placeholder, which fill()
    turns into --runtime (a Loom link pasted by hand leaves it there)."""
    end = _preview_end(text)
    return end >= 0 and "[N]-min" in text[:end]


def runtime_placeholder_below(text: str) -> bool:
    """Whether `[N]-min` is still in the text after the preview, where fill()
    also writes --runtime."""
    end = _preview_end(text)
    return "[N]-min" in (text[end:] if end >= 0 else text)


def runtime_warning(tokens: List[str], runtime: int, placeholder: bool = False,
                    below: bool = False) -> Optional[str]:
    """Why --runtime could not be applied to a preview with these `<n>-min`
    tokens (none, or several: which one is the runtime is a guess), or None
    when it has exactly one, or still has the `[N]-min` placeholder
    (`placeholder`): fill() fills that with --runtime and leaves the real
    tokens alone (see runtime_kept). `below`: `[N]-min` after the preview,
    which fill() still fills, so the warning says only the preview missed it."""
    if placeholder:
        return None
    where = (" to the preview ([N]-min further down still becomes {}-min)".format(int(runtime))
             if below else "")
    if len(tokens) > 1:
        return ("the preview has several <n>-min tokens ({}), so --runtime {} was not "
                "applied{}. Edit the runtime by hand.".format(", ".join(tokens), runtime, where))
    if not tokens:
        return ("the preview has no <n>-min token, so --runtime {} was not applied{}. "
                "Add the runtime by hand.".format(runtime, where))
    return None


def runtime_kept(tokens: List[str], runtime: int) -> str:
    """The real `<n>-min` tokens a preview with the `[N]-min` placeholder keeps
    as they are, for the message ("15-min left as it is"), or "" when every
    one already says --runtime (nothing to point out)."""
    kept = [t for t in tokens if t != "{}-min".format(int(runtime))]
    if not kept:
        return ""
    return "{} left as {}".format(", ".join(kept), "it is" if len(kept) == 1 else "they are")


def replace_loom(text: str, loom: str, runtime: int) -> str:
    """Swap the filled Loom link (every token of that video, whole) and the
    preview's `<n>-min` runtime token, only when it has exactly one and no
    `[N]-min` placeholder (with several, which one is the runtime is a guess,
    so none is touched; with the placeholder, fill() puts the runtime there
    and a real token is text the author typed)."""
    old = existing_loom(text)
    if old:
        text = set_loom(text, loom_id(old) or "", loom)
    if len(runtime_tokens(text)) == 1 and not runtime_placeholder(text):
        text = set_runtime(text, runtime)
    return text


def logged_rows(csv_path: str, job_url: str) -> List[Dict[str, str]]:
    """Rows of proposals.csv already logged for `job_url`, as csv.DictReader
    reads them: the reference the in-place rewrite is checked against."""
    return [row for _, row in _logged(csv_path, job_url)]


def _logged(csv_path: str, job_url: str) -> List[Tuple[int, Dict[str, str]]]:
    """(line the row starts on, row) for each row of logged_rows."""
    if not job_url or not os.path.exists(csv_path):
        return []
    found: List[Tuple[int, Dict[str, str]]] = []
    with open(csv_path, "r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            if (row.get("job_url") or "").strip() != job_url:
                continue
            # The reader has just read the row's last line; a line break
            # inside a quoted field is one more line of the same row. Extra
            # fields sit in a list under the None key.
            values: List[str] = []
            for value in row.values():
                values.extend(value if isinstance(value, list) else [value or ""])
            breaks = sum(len(_LINE_BREAK.findall(v)) for v in values)
            found.append((reader.reader.line_num - breaks, row))
    return found


def write_atomic(path: str, text: str) -> None:
    """Write via a temp file in the same folder and os.replace, keeping the
    original file's mode, so a crash never leaves a half-written file. Line
    endings are written exactly as they are in `text`."""
    directory = os.path.dirname(os.path.abspath(path))
    mode = stat.S_IMODE(os.stat(path).st_mode) if os.path.exists(path) else None
    fd, tmp = tempfile.mkstemp(prefix=".{}.".format(os.path.basename(path)),
                               suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        if mode is not None:
            os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def log_row(job_dir: str, loom: str, variant: str, visible_chars: Optional[int],
            now: Optional[datetime.datetime] = None,
            meta: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """`meta`: apply_meta.meta_for() columns (job_created_utc, age_hours_at_apply,
    connects, boosted); only those keys are taken, blank when missing."""
    spec_path = os.path.join(job_dir, "spec.json")
    url, title = jd_fields(job_dir)
    if os.path.exists(spec_path):
        spec = WorkflowSpec.load(spec_path)
        platform, slug, nodes = platform_label(spec), slugify(spec.title), str(len(spec.flow_nodes))
    elif os.path.exists(os.path.join(job_dir, "deck-spec.json")):
        # Source-only decks render in the shared queue, outside the job folder.
        # Count the first workflow, matching the platform recorded for that scene.
        # Validate only the metadata we consume; deck rendering owns its full schema.
        with open(os.path.join(job_dir, "deck-spec.json"), encoding="utf-8") as fh:
            deck = json.load(fh)
        scenes = deck.get("scenes") if isinstance(deck, dict) else None
        if not isinstance(scenes, list) or not scenes or any(
                not isinstance(scene, dict) or not isinstance(scene.get("kind"), str)
                for scene in scenes):
            raise ValueError("deck-spec.json: scenes must be a nonempty list of scene objects with kind strings")
        workflow = next((scene for scene in scenes if scene["kind"] == "workflow"), None)
        if workflow is None:
            raise ValueError("deck-spec.json: requires a workflow scene")
        platform = workflow.get("platform")
        if not isinstance(platform, str) or platform not in ("ghl", "n8n", "make", "claude-code", "codex"):
            raise ValueError("deck-spec.json: first workflow platform must be ghl, n8n, make, claude-code or codex")
        content = workflow.get("content")
        flow_nodes = content.get("nodes") if isinstance(content, dict) else None
        if not isinstance(flow_nodes, list) or not flow_nodes or any(
                not isinstance(node, dict) or not isinstance(node.get("id"), str)
                or not node["id"].strip() for node in flow_nodes):
            raise ValueError("deck-spec.json: first workflow content.nodes must be a nonempty list of objects with string ids")
        if len({node["id"] for node in flow_nodes}) != len(flow_nodes):
            raise ValueError("deck-spec.json: first workflow node ids must be unique")
        slug = os.path.basename(os.path.normpath(job_dir))
        nodes = str(len(flow_nodes))
    elif any(os.path.exists(os.path.join(job_dir, f)) for f in ("prototype.html", "page.html")):
        # Prototype-only jobs have no spec: log the prototype itself.
        platform, slug, nodes = "prototype", os.path.basename(os.path.normpath(job_dir)), ""
    elif os.path.exists(os.path.join(job_dir, "beats.md")):
        # Loom-only jobs (a screen-share of a real system, no page): log the Loom.
        platform, slug, nodes = "loom-only", os.path.basename(os.path.normpath(job_dir)), ""
    else:
        raise FileNotFoundError(spec_path)
    row = {key: "" for key in CSV_HEADER}
    row.update({
        "applied_at": (now or datetime.datetime.now()).isoformat(timespec="minutes"),
        "job_title": title,
        "job_url": url,
        "platform": platform,
        "build_slug": slug,
        "node_count": nodes,
        "loom_url": loom,
        "opener_variant": variant or "do-x-all-the-time",
        "opener_visible_chars": "" if visible_chars is None else str(visible_chars),
    })
    for key in apply_meta.META_FIELDS:
        row[key] = (meta or {}).get(key) or ""
    return row


def append_row(csv_path: str, row: Dict[str, str]) -> None:
    """Append in the file's own column order; create it with the standard
    header if it does not exist yet."""
    header = CSV_HEADER
    exists = os.path.exists(csv_path) and os.path.getsize(csv_path) > 0
    if exists:
        with open(csv_path, "r", encoding="utf-8", newline="") as fh:
            first = next(csv.reader(fh), None)
        if first:
            header = first
        with open(csv_path, "rb") as fh:
            fh.seek(-1, os.SEEK_END)
            needs_newline = fh.read(1) not in (b"\n", b"\r")
    else:
        needs_newline = False
    with open(csv_path, "a", encoding="utf-8", newline="") as fh:
        if needs_newline:
            fh.write("\n")
        writer = csv.DictWriter(fh, fieldnames=header, extrasaction="ignore",
                                lineterminator="\n")
        if not exists:
            writer.writeheader()
        writer.writerow({key: row.get(key, "") for key in header})


# csv.reader's quote states (excel dialect, which proposals.csv is read with).
_START, _UNQUOTED, _QUOTED, _QUOTE_IN_QUOTED = range(4)


def _step(state: int, char: str) -> int:
    """csv.reader's quote state after `char`, for a character that does not
    end the record. A `"` opens a quoted field only as a field's first
    character; anywhere else in an unquoted field it is an ordinary character
    (a hand-typed `55" monitor`). Inside a quoted field `""` is an escaped
    quote, and text after the closing quote runs on unquoted to the next `,`
    (csv is not strict)."""
    if state == _QUOTED:
        return _QUOTE_IN_QUOTED if char == '"' else _QUOTED
    if char == ",":
        return _START
    if char == '"' and state in (_START, _QUOTE_IN_QUOTED):
        return _QUOTED  # opens the field, or `""` inside it
    return _UNQUOTED


def _split_records(text: str) -> List[Tuple[str, str]]:
    """[(record, terminator)] with "".join(r + t) == text, cut exactly where
    csv.reader (on the file opened with newline="", as logged_rows reads it)
    ends a row: at `\n`, `\r\n` or `\r` outside a quoted field (see _step).
    A line break inside a quoted field stays in its record; the terminator is
    kept as found, or "" for a last line without one."""
    out: List[Tuple[str, str]] = []
    start, i, n, state = 0, 0, len(text), _START
    while i < n:
        char = text[i]
        if state != _QUOTED and char in "\r\n":
            term = "\r\n" if text.startswith("\r\n", i) else char
            out.append((text[start:i], term))
            i += len(term)
            start, state = i, _START
            continue
        state = _step(state, char)
        i += 1
    if start < n:
        out.append((text[start:], ""))
    return out


def _split_fields(record: str) -> List[str]:
    """The raw text of each field of one record, quotes and all, cut at the
    commas csv.reader splits on (see _step)."""
    fields, start, state = [], 0, _START
    for i, char in enumerate(record):
        if state != _QUOTED and char == ",":
            fields.append(record[start:i])
            start = i + 1
        state = _step(state, char)
    fields.append(record[start:])
    return fields


def _csv_field(value: str) -> str:
    if any(c in value for c in ',"\r\n'):
        return '"{}"'.format(value.replace('"', '""'))
    return value


def rewrite_logged(text: str, job_url: str, updates: Dict[str, str]) -> Tuple[str, int]:
    """proposals.csv text with `updates` applied to every row whose job_url is
    `job_url`, and the number of rows it matched. Only those fields' bytes
    change: every other field, row, quote and line ending is kept as it was.
    Raises ValueError when the file cannot be edited that surgically. The
    caller checks the count against logged_rows (what csv reads)."""
    records = _split_records(text)
    if not records:
        raise ValueError("the log is empty")

    def values(record: str) -> List[str]:
        return next(csv.reader(io.StringIO(record, newline="")), [])

    header = values(records[0][0])
    missing = [c for c in ["job_url"] + list(updates) if c not in header]
    if missing:
        raise ValueError("no {} column in the log header".format(", ".join(missing)))
    url_at = header.index("job_url")
    changed = 0
    out = []
    for index, (record, term) in enumerate(records):
        if index == 0 or not record:
            out.append(record + term)
            continue
        parsed = values(record)
        if len(parsed) <= url_at or parsed[url_at].strip() != job_url:
            out.append(record + term)
            continue
        raw = _split_fields(record)
        if len(raw) != len(parsed) or any(
                values(r)[:1] != [p] and not (r == "" and p == "") for r, p in zip(raw, parsed)):
            raise ValueError("row {} does not split cleanly into fields".format(index + 1))
        for column, value in updates.items():
            at = header.index(column)
            while len(raw) <= at:
                raw.append("")
            raw[at] = _csv_field(value)
        out.append(",".join(raw) + term)
        changed += 1
    return "".join(out), changed


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="upwork_gen.finalize", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("job_dir")
    parser.add_argument("--loom", required=True, help="the real https://www.loom.com/share/... URL")
    parser.add_argument("--runtime", required=True, type=int, help="Loom length in minutes")
    parser.add_argument("--start", required=True, help='replaces [START], e.g. "today"')
    parser.add_argument("--draft", help="replaces [DRAFT]")
    parser.add_argument("--name", help='client first name: "Hey [greeting]" or "Hey there" -> "Hey <Name>"')
    parser.add_argument("--variant", default="do-x-all-the-time",
                        help="opener_variant for the log (the old Template A opener is "
                             "'template-a-all-the-time', never 'standard', which is one "
                             "custom-opener row)")
    parser.add_argument("--replace-loom", action="store_true",
                        help="the Loom URL is already filled: swap it (and the <n>-min "
                             "runtime) for --loom/--runtime")
    parser.add_argument("--relog", action="store_true",
                        help="append a proposals.csv row even if this job_url is logged "
                             "(a second row never gets outcomes: sync_outcomes lets one row "
                             "claim each job)")
    parser.add_argument("--no-log", action="store_true", help="do not append to proposals.csv")
    parser.add_argument("--no-copy", action="store_true", help="do not pbcopy the proposal")
    parser.add_argument("--csv", default=PROPOSALS_CSV, help=argparse.SUPPRESS)
    parser.add_argument("--posted", help="job_created_utc, the job's ISO posting time in UTC "
                                         "(default: jd.txt created_utc: line, else its Posted date)")
    parser.add_argument("--connects", type=int,
                        help="connects to apply (default: 'Connects to apply: N' in jd.txt)")
    parser.add_argument("--boosted", choices=["yes", "no"], help="whether the proposal is boosted")
    args = parser.parse_args(argv)
    # Normalised once: fill() and the re-run's rename check see the same name,
    # so a blank --name never touches the greeting.
    name = normalize_name(args.name)

    job_dir = os.path.abspath(args.job_dir)
    path = os.path.join(job_dir, "proposal.md")
    text = read_text(path)
    if text is None:
        print("  no proposal.md in {}".format(job_dir), file=sys.stderr)
        return 2
    loom = normalize_loom(args.loom)
    if loom is None:
        print("  --loom must be a Loom share link, https://www.loom.com/share/<video id> "
              "(got {!r}); the preview is counted through https://www.loom".format(
                  args.loom.strip()), file=sys.stderr)
        return 2
    if loom != args.loom.strip():
        print("  loom:    using {} (from {})".format(loom, args.loom.strip()))
    video = loom_id(loom) or ""

    job_url = ""
    if not args.no_log:
        job_url = jd_fields(job_dir)[0]
        if not job_url:
            # Without a url a re-run cannot tell it already logged this job,
            # and sync_outcomes can only match the row on its title.
            print("  REFUSED: jd.txt has no 'url: <upwork job url>' line, so the log row could "
                  "not be matched to this job. Add it as line 1 of jd.txt, or pass --no-log; "
                  "nothing written.", file=sys.stderr)
            return 2

    replaced = retimed = renamed = False
    rerun = "[LOOMURL]" not in text
    before_length = preview_length(text) if rerun else None
    if rerun:
        # A re-run that turns "Hey there" into "Hey <Name>" changes the
        # preview count, so the logged row follows it like a runtime change.
        renamed = name is not None and (GREETING_PLACEHOLDER in text
                                        or ("Hey there" in text and name != "there"))
        current = existing_loom(text)
        if current is None:
            print("  REFUSED: proposal.md has neither [LOOMURL] nor a loom.com/share URL; "
                  "nothing written.", file=sys.stderr)
            return 2
        if loom_id(current) != video:
            if not args.replace_loom:
                print("  REFUSED: proposal.md is already finalized with {}.\n"
                      "  Pass --replace-loom to swap it for {}; nothing written."
                      .format(current, loom), file=sys.stderr)
                return 2
            was = runtime_tokens(text)
            placeholder = runtime_placeholder(text)
            below = runtime_placeholder_below(text)
            warning = runtime_warning(was, args.runtime, placeholder, below)
            text = replace_loom(text, loom, args.runtime)
            replaced = True
            if warning:
                note = "runtime not applied to the preview" if below else "runtime not applied"
            elif placeholder and runtime_kept(was, args.runtime):
                note = "[N]-min -> {}-min; {}".format(int(args.runtime),
                                                      runtime_kept(was, args.runtime))
            else:
                note = "{}-min".format(int(args.runtime))
            print("  replaced loom: {} -> {} ({})".format(current, loom, note))
            if warning:
                print("  WARNING: " + warning)
        else:
            tidied = set_loom(text, video, loom)
            if tidied != text:
                print("  already finalized with this Loom video; link tidied to {}".format(loom))
            else:
                print("  already finalized with this Loom URL; filling anything left")
            # The same video with a corrected --runtime: the preview's
            # `<n>-min` follows it, and so does the logged count below. Only
            # when it is the preview's one such token and there is no
            # `[N]-min` placeholder; with several, which one is the runtime
            # is a guess, so none is touched, and with the placeholder
            # fill() fills only that.
            text = tidied
            was = runtime_tokens(tidied)
            want = "{}-min".format(int(args.runtime))
            placeholder = runtime_placeholder(tidied)
            warning = runtime_warning(was, args.runtime, placeholder,
                                      runtime_placeholder_below(tidied))
            if warning:
                print("  WARNING: " + warning)
            elif placeholder and not was:
                print("  runtime: [N]-min -> {} in the preview".format(want))
            elif placeholder:
                # The real tokens are the author's text: fill() fills only
                # the placeholder. Silent when they already say --runtime.
                kept = runtime_kept(was, args.runtime)
                if kept:
                    print("  runtime: [N]-min -> {} in the preview; {}".format(want, kept))
            elif was[0] != want:
                text = set_runtime(tidied, args.runtime)
                retimed = True
                print("  runtime: {} -> {} in the preview".format(was[0], want))

    filled, remaining = fill(text, loom, args.runtime, args.start, args.draft, name)
    blocking = [p for p in REQUIRED_GONE if p in remaining]
    if blocking:
        print("  REFUSED: {} would remain in proposal.md; nothing written.".format(
            ", ".join(blocking)), file=sys.stderr)
        return 2

    length = preview_length(filled)
    body = filled.lstrip()
    preview = body[: length] if length is not None else ""
    print("\n  preview ({} chars): {}".format(length, preview))
    if length is None or not (PREVIEW_MIN <= length <= PREVIEW_MAX):
        print("  REFUSED: preview is {} chars, outside {}-{}. Edit the opener in "
              "proposal.md, then re-run; nothing written.".format(
                  length, PREVIEW_MIN, PREVIEW_MAX), file=sys.stderr)
        return 2
    signoffs = sum(1 for line in filled.splitlines() if line.strip() == "Lorenzo")
    if signoffs > 1:
        print("  REFUSED: proposal.md signs off 'Lorenzo' {} times; keep one, then re-run; "
              "nothing written.".format(signoffs), file=sys.stderr)
        return 2
    others = [p for p in remaining if p not in REQUIRED_GONE]
    if others:
        print("  WARNING: still in the proposal: {}".format(", ".join(others)))
    if args.name is not None and name is None:
        print("  note: --name is blank, the greeting is left as it is")
    elif name and "Hey there" not in text and GREETING_PLACEHOLDER not in text:
        print("  note: no 'Hey there' or 'Hey [greeting]' found, --name had nothing to replace")

    # After --replace-loom, a runtime change or a greeting-name change the
    # logged row must follow the proposal. Work the rewrite out before writing anything, so a log that
    # cannot be edited safely leaves both files as they were.
    updates: Dict[str, str] = {}
    if replaced:
        updates["loom_url"] = loom
    # Any other re-run edit that moves the preview count ([DRAFT] or [START]
    # left in the opener, say) is caught by comparing the counts.
    recounted = rerun and length != before_length
    if replaced or retimed or renamed or recounted:
        updates["opener_visible_chars"] = "" if length is None else str(length)
    found: List[Tuple[int, Dict[str, str]]] = []
    rewritten: Optional[Tuple[str, str, int]] = None  # (log before, log after, rows)
    if not args.no_log:
        found = _logged(args.csv, job_url)
        if found and updates:
            with open(args.csv, "r", encoding="utf-8", newline="") as fh:
                log_text = fh.read()
            try:
                new_text, matched = rewrite_logged(log_text, job_url, updates)
            except ValueError as exc:
                print("  REFUSED: cannot update the logged row for {} in {} ({}); "
                      "nothing written.".format(job_url, args.csv, exc), file=sys.stderr)
                return 2
            if matched != len(found):
                # csv and the in-place edit disagree about where the rows are:
                # writing now would report success and leave a stale row.
                print("  REFUSED: {} has {} row(s) for {} ({}) but the in-place edit matched "
                      "{}, so the log would not follow the proposal. A quote or line break "
                      "in another row may be merging rows. Set {} on {} by hand, then "
                      "re-run with --no-log; nothing written.".format(
                          args.csv, len(found), job_url,
                          "; ".join("line {}, applied_at {}".format(
                              line, row.get("applied_at") or "?") for line, row in found),
                          matched,
                          " and ".join("{} {}".format(k, v or '""') for k, v in updates.items()),
                          "that row" if len(found) == 1 else "those rows"),
                      file=sys.stderr)
                return 2
            rewritten = (log_text, new_text, matched)
    already = [row for _, row in found]
    # Everything the log needs (spec.json, jd.txt) is read before the first
    # write: a broken spec leaves proposal.md and the log as they were.
    row: Dict[str, str] = {}
    if not args.no_log:
        try:
            now = datetime.datetime.now()
            row = log_row(job_dir, loom, args.variant, length, now=now,
                          meta=apply_meta.meta_for(job_dir, now, args.posted, args.connects,
                                                   args.boosted))
        except Exception as exc:  # noqa: BLE001 - any load failure refuses
            print("  REFUSED: cannot build the log row from {} ({}: {}); nothing written."
                  .format(job_dir, type(exc).__name__, exc), file=sys.stderr)
            return 2

    write_atomic(path, filled)
    print("  wrote:   {}".format(path))

    if not args.no_copy:
        try:
            subprocess.run(["pbcopy"], input=filled.encode("utf-8"), check=False)
            print("  clipboard: full proposal ready to paste")
        except OSError:
            print("  clipboard: pbcopy unavailable")

    if not args.no_log:
        if rewritten is not None:
            log_text, new_text, matched = rewritten
            if new_text != log_text:
                write_atomic(args.csv, new_text)
                print("  log:     updated {} in place on {} existing row(s) for {} in {}".format(
                    " and ".join(updates), matched, job_url, args.csv))
            else:
                print("  log:     {} already current on {} existing row(s) for {} in {}".format(
                    " and ".join(updates), matched, job_url, args.csv))
            if args.relog:
                append_row(args.csv, row)
                print("  logged:  {} -> {} (--relog)".format(row["build_slug"], args.csv))
        elif already and not args.relog:
            print("  NOT LOGGED: {} already has {} row(s) in {} (first applied_at {}). "
                  "Pass --relog to add another.".format(
                      row["job_url"], len(already), args.csv,
                      already[0].get("applied_at") or "?"))
        else:
            append_row(args.csv, row)
            print("  logged:  {} -> {}".format(row["build_slug"], args.csv))
            print("  apply:   {}".format(apply_meta.describe(row)))
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
