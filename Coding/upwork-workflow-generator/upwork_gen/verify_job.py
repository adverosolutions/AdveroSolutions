"""Automated verification pass plus a genericness lint for one or more job folders.

    python3 -m upwork_gen.verify_job <job_dir> [<job_dir> ...]
    python3 -m upwork_gen.verify_job --order N      # first N slugs of jobs/_ORDER.txt

This is the "Verification pass" from the /upwork skill, made mechanical:

* FAIL  — something that imports badly, reads wrong on camera, or breaks the
          locked proposal format. Exit code 1 when any job has one.
* WARN  — the genericness lint: the build is valid but has tells that it was
          not written for this client (example.com URLs, prompts that just
          repeat the node name, default parser schemas, charts cloned from an
          archetype, a client name that appears nowhere).
"""

from __future__ import annotations

import argparse
import difflib
import glob
import json
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional, Tuple

from .generate import ROOT, VAULT_DIR, ascii_safe
from .spec import AI_SUB_KINDS, WorkflowSpec, slugify

# The pipeline folder sits next to the tool; overridable so tests never touch it.
UP_ROOT = os.environ.get("UPWORK_PIPELINE") or os.path.join(
    os.path.dirname(ROOT), "upwork-pipeline")
JOBS_DIR = os.path.join(UP_ROOT, "jobs")
ORDER_PATH = os.path.join(JOBS_DIR, "_ORDER.txt")

# n8n / Make canvases aim for 10-15 nodes, easy to walk through on camera (Lorenzo,
# 2026-09-24): every node except stickies counts, Config and error path included.
# A target, not a cap: above it is a WARN, fine when the post needs the nodes.
MAX_CANVAS_NODES = 15
# The number each case study must carry, word for word (templates/ps-case-studies.md).
PROOF_FACTS = ("$750M+ in annual bid volume", "$5M in loan applications in 30 days",
               "qualified lead volume 35%", "AI agency to $10,000 a month")
# Billing words that never belong in a proposal (Lorenzo, 2026-09-24, hard stop).
BILLING = re.compile(
    r"\bretainers?\b|\$\s?\d|\bper hour\b|\ban hour\b|\bhourly\b|/hr\b|\bbilling\b|"
    r"\bbilled\b|\bbudget\b|\bfees?\b|\bmy rates?\b|\bfixed[- ]price\b|\bpayment\b|"
    r"\bmy (?:price|pricing)\b|\bcharge\b|\binvoice me\b", re.I)
PREVIEW_MIN = 133
PREVIEW_MAX = 150
LOOM_MARK = "https://www.loom"
LOOM_SHARE = "https://www.loom.com/share/"
LOOM_PLACEHOLDER = LOOM_SHARE + "[LOOMURL]"
# What the locked format accepts at the link: the placeholder, or a video id
# with at most one query string (`?sid=...`), then whitespace or the end of
# the text. A trailing slash, a second `?`, a fragment or anything else glued
# to the id fails.
_LOOM_LINK = re.compile(
    r"https://www\.loom\.com/share/(?:\[LOOMURL\]|[A-Za-z0-9]+(?:\?[^\s?#]*)?)(?=\s|\Z)")
# The whole share-link token as it sits in a proposal: group 1 is the video
# id, group 2 whatever is glued to it (`/`, `?sid=...`, junk from an earlier
# bad replace) up to the next whitespace. Sentence punctuation right before
# the whitespace stays outside the token.
LOOM_TOKEN = re.compile(
    r"https://www\.loom\.com/share/([A-Za-z0-9]+)(\S*?)(?=[.,;:!)\]}'\"]*(?:\s|\Z))")

ACCEPTABLE_SPEC_WARNINGS = (
    re.compile(r"^\d+ trigger nodes; n8n renders these side by side$"),
    re.compile(r"^no trigger node\b"),
)

# "3 - ", "4b - ", "12. " — the step prefix every node label carries.
_STEP_PREFIX = re.compile(r"^\s*(\d+)[a-z]?\s*[-.:·]\s*")

# Every file a compile puts in a job folder. `batch` copies exactly these and
# moves any it did not produce into <job>/.stale/.
BUILD_SUFFIXES = (
    ".n8n.json", ".make.json", ".excalidraw", ".mmd.md", ".ghl.json",
    ".ghl-prompt.txt", ".ghl-prompt-oneline.txt", ".ghl-prereqs.txt",
    # The builder mockup: every GHL compile writes <slug>.ghl.html, a Zapier
    # one <slug>.zapier.html. Always one per spec, never split.
    ".ghl.html", ".zapier.html",
)
GHL_SUFFIXES = (".ghl.json", ".ghl-prompt.txt", ".ghl-prompt-oneline.txt", ".ghl-prereqs.txt")
# The preview placeholder for the Loom runtime: "[N]-min" becomes "1-min".
RUNTIME_PLACEHOLDER = "[N]"

DEFAULT_PARSER_EXAMPLE = {"summary": "text", "score": 1}
CLONE_RATIO = 0.6
CLONE_SHARE = 0.5


@dataclass
class JobReport:
    job_dir: str
    slug: str
    platform: str = "?"
    nodes: int = 0
    preview_len: Optional[int] = None
    url: str = ""
    title: str = ""
    fails: List[str] = field(default_factory=list)
    warns: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.fails


# --------------------------------------------------------------------------
# Small helpers shared with finalize / batch
# --------------------------------------------------------------------------


def read_text(path: str) -> Optional[str]:
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def preview_of(text: str) -> Optional[str]:
    """The Upwork preview: everything up to and including the first
    `https://www.loom`. None when the proposal has no Loom link at all."""
    body = text.lstrip()
    index = body.find(LOOM_MARK)
    if index < 0:
        return None
    return body[: index + len(LOOM_MARK)]


def count_preview(preview: str) -> int:
    """Visible length of a preview. An unfilled `[N]` counts as 1 character:
    it becomes the one-digit Loom runtime."""
    return len(preview) - (len(RUNTIME_PLACEHOLDER) - 1) * preview.count(RUNTIME_PLACEHOLDER)


def preview_length(text: str) -> Optional[int]:
    preview = preview_of(text)
    return None if preview is None else count_preview(preview)


def build_suffix(name: str) -> Optional[str]:
    """The build suffix of a file name (`.n8n.json`, `.ghl-prereqs.txt`, ...),
    or None when it is not a compile output."""
    for suffix in sorted(BUILD_SUFFIXES, key=len, reverse=True):
        if name.endswith(suffix):
            return suffix
    return None


def ghl_part(name: str, slug: str) -> Optional[int]:
    """n for `<slug>--<n>-<trigger>.<ghl suffix>`, else None."""
    suffix = build_suffix(name)
    if suffix not in GHL_SUFFIXES:
        return None
    match = re.match(r"^{}--(\d+)-.+$".format(re.escape(slug)), name[: -len(suffix)])
    return int(match.group(1)) if match else None


def is_current_build(name: str, slug: str) -> bool:
    """True when `name` is a compile output of the spec whose slug is `slug`:
    `<slug><suffix>`, or `<slug>--<n>-<trigger><ghl suffix>` for a spec split
    into several GHL workflows."""
    suffix = build_suffix(name)
    if suffix is None:
        return False
    return name[: -len(suffix)] == slug or ghl_part(name, slug) is not None


def ghl_plain_and_split(names: List[str], slug: str) -> Tuple[List[str], List[str]]:
    """(plain `<slug>.<ghl suffix>` names, split `<slug>--<n>-<trigger>.<ghl
    suffix>` names) among `names`. One compile writes one set or the other,
    never both, so seeing both means one of them is left over from an older
    run of the same title."""
    plain = sorted(n for n in names if n in {slug + s for s in GHL_SUFFIXES})
    split = sorted(n for n in names if ghl_part(n, slug) is not None)
    return plain, split


STALE_DIR = ".stale"
# `.stale/` names: `<name>`, `<YYYYmmdd-HHMMSS>.<name>` or
# `<YYYYmmdd-HHMMSS>.<n>.<name>` (see cli._retire_stale).
_STALE_STAMP = re.compile(r"^\d{8}-\d{6}\.(?:\d+\.)?")


def stale_slugs(job_dir: str) -> List[str]:
    """Build slugs of the files batch retired into `<job>/.stale/`: the job's
    own earlier titles."""
    stale_dir = os.path.join(job_dir, STALE_DIR)
    if not os.path.isdir(stale_dir):
        return []
    slugs = set()
    for name in os.listdir(stale_dir):
        name = _STALE_STAMP.sub("", name)
        suffix = build_suffix(name)
        if suffix is None:
            continue
        stem = name[: -len(suffix)]
        if suffix in GHL_SUFFIXES:
            stem = re.sub(r"--\d+-.+$", "", stem)
        if stem:
            slugs.add(stem)
    return sorted(slugs)


def strip_step(label: str) -> str:
    return _STEP_PREFIX.sub("", label or "").strip()


def step_number(label: str) -> Optional[int]:
    match = _STEP_PREFIX.match(label or "")
    return int(match.group(1)) if match else None


def jd_fields(job_dir: str) -> Tuple[str, str]:
    """(url, title) from jd.txt: `url: ...` on line 1, the title on line 2."""
    text = read_text(os.path.join(job_dir, "jd.txt")) or ""
    lines = text.splitlines()
    url = ""
    for line in lines[:5]:
        if line.lower().startswith("url:"):
            url = line.split(":", 1)[1].strip()
            break
    title = lines[1].strip() if len(lines) > 1 else ""
    return url, title


def is_chart(spec: WorkflowSpec) -> bool:
    return spec.platform == "diagram" or not any(n.is_trigger for n in spec.flow_nodes)


def platform_label(spec: WorkflowSpec) -> str:
    """n8n | make | gohighlevel | chart (diagram, or no trigger at all)."""
    if spec.platform == "diagram":
        return "chart"
    if not any(n.is_trigger for n in spec.flow_nodes):
        return "chart"
    return spec.platform


def order_slugs(count: int, jobs_dir: Optional[str] = None,
                missing: Optional[List[str]] = None) -> List[str]:
    """Folders of the first `count` slugs in _ORDER.txt. A listed slug with no
    folder is reported (and appended to `missing` when given), never skipped
    silently."""
    jobs_dir = jobs_dir or JOBS_DIR
    path = os.path.join(jobs_dir, "_ORDER.txt")
    text = read_text(path)
    if text is None:
        raise SystemExit("no {}".format(path))
    slugs = [line.strip() for line in text.splitlines() if line.strip()]
    found = []
    for slug in slugs[:count]:
        if os.path.isdir(os.path.join(jobs_dir, slug)):
            found.append(os.path.join(jobs_dir, slug))
        else:
            print("  slug {} listed in _ORDER.txt has no folder".format(slug))
            if missing is not None:
                missing.append(slug)
    return found


def _is_ascii(text: str) -> bool:
    try:
        text.encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


def _first_non_ascii(text: str) -> str:
    for index, char in enumerate(text):
        if ord(char) > 127:
            return "{!r} at offset {}".format(char, index)
    return ""


def _walk(value: Any, path: str = "") -> Iterator[Tuple[str, Any]]:
    """Every (path, leaf) in a JSON value."""
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _walk(child, "{}.{}".format(path, key) if path else str(key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk(child, "{}[{}]".format(path, index))
    else:
        yield path, value


def _rl_value(value: Any) -> str:
    """A resource-locator field ({"__rl": true, "value": ...}) or a plain string."""
    if isinstance(value, dict):
        return str(value.get("value") or value.get("cachedResultName") or "").strip()
    return str(value or "").strip()


# --------------------------------------------------------------------------
# Proposal and beats
# --------------------------------------------------------------------------


def proof_bank() -> List[str]:
    """The case-study bullets, word for word, from templates/ps-case-studies.md."""
    text = read_text(os.path.join(UP_ROOT, "templates", "ps-case-studies.md")) or ""
    return [line.rstrip() for line in text.splitlines() if line.startswith("-> ")]


def check_proposal(text: str) -> Tuple[List[str], Optional[int]]:
    """FAIL items for the locked proposal format, plus the preview length."""
    fails: List[str] = []
    preview = preview_of(text)
    length = None if preview is None else count_preview(preview)
    if preview is None:
        fails.append("proposal: no {} link, so no preview can be counted".format(LOOM_MARK))
    elif not (PREVIEW_MIN <= length <= PREVIEW_MAX):
        fails.append("proposal: preview is {} chars through {} (needs {}-{})".format(
            length, LOOM_MARK, PREVIEW_MIN, PREVIEW_MAX))

    if preview is not None:
        body = text.lstrip()
        start = body.find(LOOM_MARK)
        if not _LOOM_LINK.match(body, start):
            snippet = body[start:start + 60].split()[0] if body[start:].split() else ""
            fails.append("proposal: link must be {} or a real loom.com/share/ URL, found {!r}"
                         .format(LOOM_PLACEHOLDER, snippet))

    if "—" in text:
        fails.append("proposal: contains an em dash ({}x)".format(text.count("—")))

    walks = len(re.findall(r"the video walks through", text, re.I))
    if walks != 1:
        fails.append("proposal: 'The video walks through' appears {} times (needs exactly 1)"
                     .format(walks))

    ps = re.search(r"P\.S\.", text)
    if not ps:
        fails.append("proposal: no P.S. block")
    else:
        bullets = [line for line in text[ps.end():].splitlines() if line.startswith("-> ")]
        if len(bullets) != 4:
            fails.append("proposal: {} '-> ' lines after P.S. (needs exactly 4)".format(
                len(bullets)))
        # The facts are fixed; the framing around them fits the job (Lorenzo,
        # 2026-09-24): each case study appears once, with its number intact.
        if proof_bank():
            for anchor in PROOF_FACTS:
                hits = sum(1 for b in bullets if anchor in b)
                if hits != 1:
                    fails.append("proposal: P.S. needs the {} case study exactly once, number "
                                 "intact (found {})".format(anchor, hits))

    # Hard stop (Lorenzo, 2026-09-24): no billing of any kind above the P.S.
    # (the case-study bullets' dollar figures are results, not prices).
    above = text[:ps.start()] if ps else text
    billing = sorted(set(m.group(0).lower() for m in BILLING.finditer(above)))
    if billing:
        fails.append("proposal: talks billing ({}); prices, rates and retainers are for "
                     "the call, never the proposal".format(", ".join(billing)))

    # On a line by itself; trailing spaces (a Markdown line break) are fine.
    if not any(line.strip() == "Lorenzo" for line in text.splitlines()):
        fails.append("proposal: no 'Lorenzo' signature line")
    return fails, length


def beat_lines(text: str) -> List[str]:
    out = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(("- ", "* ")):
            out.append(stripped[2:].strip())
        elif re.match(r"\d+\.\s", stripped):
            out.append(re.sub(r"^\d+\.\s+", "", stripped))
    return out


def check_beats(text: str) -> List[str]:
    fails: List[str] = []
    beats = beat_lines(text)
    if len(beats) > 8:
        fails.append("beats: {} bullet lines (max 8)".format(len(beats)))
    for index, beat in enumerate(beats, 1):
        words = len(beat.split())
        if words > 12:
            fails.append("beats: line {} has {} words (max 12): {!r}".format(index, words, beat))
    return fails


# --------------------------------------------------------------------------
# Compiled artifacts
# --------------------------------------------------------------------------


def check_n8n(workflow: Dict[str, Any], raw: str, title: str, name: str,
              calendly_triggers: int = 0) -> List[str]:
    """`calendly_triggers`: how many spec nodes are real Calendly triggers
    (`trigger.app`, `app: calendly`). Only that many calendlyTrigger nodes are
    allowed; any more are an unmapped trigger the compiler fell back on."""
    fails: List[str] = []
    nodes = workflow.get("nodes", []) or []
    names = {n.get("name") for n in nodes}
    dangling = []
    for source, ports in (workflow.get("connections") or {}).items():
        if source not in names:
            dangling.append("source {!r}".format(source))
        for outputs in (ports or {}).values():
            for output in outputs or []:
                for link in output or []:
                    if link.get("node") not in names:
                        dangling.append("{!r} -> {!r}".format(source, link.get("node")))
    if dangling:
        fails.append("{}: {} dangling connection(s): {}".format(
            name, len(dangling), "; ".join(dangling[:5])))
    if "calendlyTrigger" in raw:
        found = sum(1 for n in nodes if "calendlyTrigger" in str(n.get("type", "")))
        if max(found, 1) > calendly_triggers:
            fails.append("{}: contains calendlyTrigger ({} node(s), {} Calendly trigger(s) "
                         "in the spec)".format(name, found, calendly_triggers))
    if not _is_ascii(raw):
        fails.append("{}: non-ASCII character {}".format(name, _first_non_ascii(raw)))
    pinned = len(workflow.get("pinData") or {})
    if pinned < 2:
        fails.append("{}: pinData on {} node(s) (needs first and last)".format(name, pinned))
    if workflow.get("name") != ascii_safe(title):
        fails.append("{}: workflow name {!r} != spec title {!r}".format(
            name, workflow.get("name"), title))
    return fails


def calendly_spec_triggers(spec: Any) -> int:
    """Spec nodes the n8n compiler turns into a real calendlyTrigger, decided the
    compiler's own way (compile_n8n): an app trigger params.trigger_stand_in
    keeps (no Webhook or Error Trigger stand-in) whose catalog entry is
    calendlyTrigger. So an app spelled "Calendly." counts exactly when it
    compiles to one."""
    if spec is None:
        return 0
    triggers = [n for n in spec.nodes if n.kind == "trigger.app"]
    if not triggers:
        return 0
    from .catalog import Catalog
    from .params import trigger_stand_in
    # A private instance: resolve() records usage, and the shared cached
    # catalog's warnings belong to the compile run, not to verify.
    catalog = Catalog("n8n")
    count = 0
    for node in triggers:
        stand_in = trigger_stand_in(node, catalog)
        if stand_in and catalog.entries.get(stand_in):
            continue  # compile_n8n swaps the stand-in's entry in
        if "calendlyTrigger" in str(catalog.resolve(node).entry.get("type", "")):
            count += 1
    return count


def _is_ai_node(node: Dict[str, Any]) -> bool:
    kind = str(node.get("type", "")).lower()
    return "langchain" in kind or "openai" in kind or "anthropic" in kind


_DEFAULT_CONTEXT_LINE = re.compile(r"^[\w .-]+:\s*\{\{\s*\$json\.[\w.]+\s*\}\}$")


def _prompt_is_label(prompt: str, node_name: str) -> bool:
    """A prompt that is just the node's own name — optionally followed by the
    compiler's default `field: {{ $json.field }}` lines — says nothing."""
    text = prompt.strip()
    if text.startswith("="):
        text = text[1:].strip()
    if not text:
        return False
    head, _, rest = text.partition("\n\n")
    candidates = {node_name.strip().lower(), strip_step(node_name).lower()}
    if head.strip().lower() not in candidates:
        return False
    return all(_DEFAULT_CONTEXT_LINE.match(line.strip())
               for line in rest.splitlines() if line.strip())


def lint_n8n(workflow: Dict[str, Any], raw: str) -> List[str]:
    """WARN items: tells that the workflow was not written for this client."""
    warns: List[str] = []
    nodes = workflow.get("nodes", []) or []
    webhook_paths: Dict[str, List[str]] = {}

    for node in nodes:
        name = str(node.get("name", ""))
        kind = str(node.get("type", ""))
        params = node.get("parameters") or {}
        if "stickyNote" in kind:
            continue

        for path, value in _walk(params):
            if isinstance(value, str) and re.search(r"https?://[^\s\"'<>]*example\.com", value):
                warns.append("lint: {!r} has an example.com URL at {}".format(name, path))
            if isinstance(value, str) and "reason_for_calling" in value:
                warns.append("lint: {!r} references reason_for_calling at {}".format(name, path))

        if _is_ai_node(node):
            for path, value in _walk(params):
                leaf = path.rsplit(".", 1)[-1]
                if leaf in ("text", "prompt", "systemMessage", "content") \
                        and isinstance(value, str) and _prompt_is_label(value, name):
                    warns.append("lint: {!r} prompt is just its node name ({})".format(name, path))

        if kind.endswith("outputParserStructured"):
            example = str(params.get("jsonSchemaExample") or "").lstrip("=").strip()
            try:
                parsed = json.loads(example) if example else None
            except ValueError:
                parsed = None
            if parsed == DEFAULT_PARSER_EXAMPLE:
                warns.append("lint: {!r} output parser still has the default "
                             "{{summary, score}} schema".format(name))

        if kind in ("n8n-nodes-base.if", "n8n-nodes-base.filter"):
            step = step_number(name)
            block = params.get("conditions") or {}
            conditions = block.get("conditions", []) if isinstance(block, dict) else []
            for condition in conditions or []:
                right = condition.get("rightValue") if isinstance(condition, dict) else None
                if step is None or right in (None, "", True, False):
                    continue
                try:
                    same = float(str(right).strip()) == float(step)
                except ValueError:
                    same = False
                if same:
                    warns.append("lint: {!r} condition compares against {!r}, its own step "
                                 "number".format(name, right))

        if kind == "n8n-nodes-base.slack":
            channel = _rl_value(params.get("channelId")) or _rl_value(params.get("channel"))
            if not channel:
                warns.append("lint: {!r} Slack node has no channel".format(name))

        if kind == "n8n-nodes-base.googleSheets":
            if not _rl_value(params.get("documentId")):
                warns.append("lint: {!r} Google Sheets node has no documentId".format(name))

        if "path" in params and ("webhook" in kind.lower() or "formTrigger" in kind):
            path_value = str(params.get("path") or "").strip()
            if path_value:
                webhook_paths.setdefault(path_value, []).append(name)

    for path_value, owners in sorted(webhook_paths.items()):
        if len(owners) > 1:
            warns.append("lint: webhook path {!r} used by {} nodes: {}".format(
                path_value, len(owners), ", ".join(repr(o) for o in owners)))
    return warns


def _sticky_texts(workflow: Dict[str, Any]) -> List[str]:
    return [str((n.get("parameters") or {}).get("content", ""))
            for n in workflow.get("nodes", []) or [] if "stickyNote" in str(n.get("type", ""))]


def lint_client(client: Dict[str, Any], title: str, workflows: List[Dict[str, Any]],
                beats_text: str) -> List[str]:
    warns: List[str] = []
    name = str(client.get("name") or "").strip()
    company = str(client.get("company") or "").strip()
    beats = beat_lines(beats_text or "")
    first_beat = beats[0] if beats else ""

    needles = [n for n in (company, name) if n]
    if needles:
        places = [title, first_beat]
        for workflow in workflows:
            places.extend(t for t in _sticky_texts(workflow) if "built for" in t.lower())
        haystack = "\n".join(places).lower()
        if not any(n.lower() in haystack for n in needles):
            warns.append("lint: client {!r} appears in neither the title, a 'Built for' "
                         "sticky, nor beat 1".format(company or name))
    if name:
        first = name.split()[0]
        if first.lower() not in first_beat.lower():
            warns.append("lint: beat 1 does not use the client's first name {!r}".format(first))
    return warns


# --------------------------------------------------------------------------
# Chart clone check
# --------------------------------------------------------------------------


def _labels_of(nodes: List[Dict[str, Any]]) -> List[str]:
    out = []
    for node in nodes:
        if node.get("kind") in AI_SUB_KINDS:
            continue
        label = strip_step(str(node.get("label", ""))).lower()
        if label:
            out.append(label)
    return out


def _similar(a: str, b: str) -> bool:
    matcher = difflib.SequenceMatcher(None, a, b)
    return (matcher.real_quick_ratio() >= CLONE_RATIO
            and matcher.quick_ratio() >= CLONE_RATIO
            and matcher.ratio() >= CLONE_RATIO)


def _source_url(text: str) -> str:
    for line in text.splitlines()[:5]:
        if line.lower().startswith("url:"):
            return line.split(":", 1)[1].strip()
    return ""


def own_archetypes(job_dir: str, spec_archetype: Optional[str] = None,
                   vault_dir: Optional[str] = None) -> Dict[str, str]:
    """{archetype id: why} for vault archetypes that are this job's own
    earlier builds, so a rebuild under a new title is not called a clone of
    itself. An archetype is the job's own only on evidence from the job
    folder:

    * its title slug is one batch retired into `<job>/.stale/`; or
    * its archived posting (vault/sources/<id>.txt, written when the build
      was learned) carries this job's `url:` line, or is this jd.txt.

    Naming an archetype in spec.json's `archetype` key (`spec_archetype`) is
    not evidence: a spec copied from another job's vault file carries that
    job's id there. It is only mentioned in the reason when the evidence
    above holds too.
    """
    vault_dir = vault_dir or VAULT_DIR
    own: Dict[str, str] = {}
    retired = set(stale_slugs(job_dir))
    jd = (read_text(os.path.join(job_dir, "jd.txt")) or "").strip()
    url = _source_url(jd)
    sources = os.path.join(os.path.dirname(os.path.abspath(vault_dir)), "sources")
    for path in sorted(glob.glob(os.path.join(vault_dir, "*.json"))):
        archetype_id = os.path.basename(path)[:-5]
        if archetype_id.startswith("_"):
            continue
        why = ""
        if retired:
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    title = str((json.load(fh) or {}).get("title", ""))
            except (OSError, ValueError, AttributeError):
                title = ""
            if title and slugify(title) in retired:
                why = "its title's builds are in .stale/"
        if not why:
            source = (read_text(os.path.join(sources, archetype_id + ".txt")) or "").strip()
            if source and jd and ((url and _source_url(source) == url) or source == jd):
                why = "learned from this job's jd.txt"
        if why:
            own[archetype_id] = ("named in spec.json; " + why
                                 if spec_archetype and archetype_id == spec_archetype else why)
    return own


def chart_overlaps(spec: WorkflowSpec, vault_dir: Optional[str] = None,
                   exempt: Optional[Dict[str, str]] = None) -> List[Tuple[str, int, int]]:
    """(archetype id, matched, total) for every archetype that shares at least
    half of this chart's step labels, best first. Archetypes in `exempt`
    (the job's own earlier builds, see own_archetypes) are skipped, and so is
    one with this chart's own title, except the archetype the spec names in
    `archetype`: a spec copied verbatim from a vault file keeps both that id
    and the title, and must not pass as the job's own build on them alone."""
    vault_dir = vault_dir or VAULT_DIR
    exempt = exempt or {}
    mine = _labels_of([n.to_dict() for n in spec.nodes])
    if not mine:
        return []
    own_title = spec.title.strip().lower()
    named = spec.archetype if isinstance(spec.archetype, str) else None
    hits: List[Tuple[str, int, int]] = []
    for path in sorted(glob.glob(os.path.join(vault_dir, "*.json"))):
        archetype_id = os.path.basename(path)[:-5]
        if archetype_id.startswith("_") or archetype_id in exempt:
            continue
        try:
            with open(path, "r", encoding="utf-8") as fh:
                other = json.load(fh)
        except (OSError, ValueError):
            continue
        if not isinstance(other, dict):
            continue
        if str(other.get("title", "")).strip().lower() == own_title and archetype_id != named:
            continue
        theirs = _labels_of(other.get("nodes", []) or [])
        if not theirs:
            continue
        matched = sum(1 for label in mine if any(_similar(label, t) for t in theirs))
        if matched / float(len(mine)) >= CLONE_SHARE:
            hits.append((archetype_id, matched, len(mine)))
    hits.sort(key=lambda h: (-h[1], h[0]))
    return hits


# --------------------------------------------------------------------------
# One job
# --------------------------------------------------------------------------


def _load_json(path: str) -> Tuple[Optional[Any], str, Optional[str]]:
    raw = read_text(path) or ""
    try:
        return json.loads(raw), raw, None
    except ValueError as exc:
        return None, raw, str(exc)


def verify(job_dir: str, vault_dir: Optional[str] = None) -> JobReport:
    job_dir = os.path.abspath(job_dir)
    report = JobReport(job_dir=job_dir, slug=os.path.basename(job_dir.rstrip("/")))
    report.url, _ = jd_fields(job_dir)

    # -- spec --------------------------------------------------------------
    spec: Optional[WorkflowSpec] = None
    raw_spec: Dict[str, Any] = {}
    spec_path = os.path.join(job_dir, "spec.json")
    if not os.path.exists(spec_path):
        report.fails.append("spec.json missing")
    else:
        try:
            spec = WorkflowSpec.load(spec_path)
            with open(spec_path, "r", encoding="utf-8") as fh:
                raw_spec = json.load(fh)
            warnings = spec.validate()
            for warning in warnings:
                if not any(p.search(warning) for p in ACCEPTABLE_SPEC_WARNINGS):
                    report.fails.append("spec: {}".format(warning))
        except Exception as exc:  # any load/validate error is the finding
            report.fails.append("spec does not load/validate: {}".format(
                str(exc).replace("\n", " ")))
            spec = None
    if spec is not None:
        report.platform = platform_label(spec)
        report.nodes = len(spec.flow_nodes)
        report.title = spec.title

    # -- stale builds: files another spec (an older title) left behind ------
    if spec is not None:
        slug = slugify(spec.title)
        foreign = sorted(name for name in os.listdir(job_dir)
                         if os.path.isfile(os.path.join(job_dir, name))
                         and build_suffix(name) and not is_current_build(name, slug))
        if foreign:
            report.fails.append("build files not from the current spec (slug {!r}): {}; "
                                "re-run batch or move them out".format(slug, ", ".join(foreign)))
        plain, split = ghl_plain_and_split(
            [n for n in os.listdir(job_dir) if os.path.isfile(os.path.join(job_dir, n))], slug)
        if plain and split:
            report.fails.append("GHL builds of slug {!r} both as one workflow ({}) and split "
                                "into several ({}); one set is from an older run. Re-run batch "
                                "or move the stale set into .stale/".format(
                                    slug, ", ".join(plain), ", ".join(split)))

    # -- n8n ---------------------------------------------------------------
    workflows: List[Dict[str, Any]] = []
    n8n_files = sorted(glob.glob(os.path.join(job_dir, "*.n8n.json")))
    if spec is not None and spec.platform == "n8n" and not n8n_files:
        report.fails.append("no *.n8n.json in the job folder (not compiled/copied)")
    for path in n8n_files:
        name = os.path.basename(path)
        workflow, raw, error = _load_json(path)
        if error or not isinstance(workflow, dict):
            report.fails.append("{}: does not parse ({})".format(name, error))
            continue
        workflows.append(workflow)
        report.fails.extend(check_n8n(workflow, raw, spec.title if spec else "", name,
                                      calendly_spec_triggers(spec)))
        on_canvas = sum(1 for n in workflow.get("nodes", []) or []
                        if "stickyNote" not in str(n.get("type", "")))
        if on_canvas > MAX_CANVAS_NODES:
            report.warns.append("{}: {} nodes on the canvas, over the 10-{} target; fine only "
                                "when every extra node is one the post needs".format(
                                    name, on_canvas, MAX_CANVAS_NODES))
        report.warns.extend(lint_n8n(workflow, raw))

    # -- make --------------------------------------------------------------
    make_files = sorted(glob.glob(os.path.join(job_dir, "*.make.json")))
    if spec is not None and spec.platform == "make" and not make_files:
        report.fails.append("no *.make.json in the job folder (not compiled/copied)")
    if spec is not None and spec.platform == "make" and len(spec.flow_nodes) > MAX_CANVAS_NODES:
        report.warns.append("{} modules in the Make scenario, over the 10-{} target; fine "
                            "only when every extra module is one the post needs".format(
                                len(spec.flow_nodes), MAX_CANVAS_NODES))
    for path in make_files:
        name = os.path.basename(path)
        _, raw, error = _load_json(path)
        if error:
            report.fails.append("{}: does not parse ({})".format(name, error))
        if not _is_ascii(raw):
            report.fails.append("{}: non-ASCII character {}".format(name, _first_non_ascii(raw)))

    # -- excalidraw --------------------------------------------------------
    scenes = sorted(glob.glob(os.path.join(job_dir, "*.excalidraw")))
    if not scenes:
        report.fails.append("no *.excalidraw chart in the job folder")
    for path in scenes:
        raw = read_text(path) or ""
        if not _is_ascii(raw):
            report.fails.append("{}: non-ASCII character {}".format(
                os.path.basename(path), _first_non_ascii(raw)))

    # -- ghl ---------------------------------------------------------------
    ghl_files = sorted(glob.glob(os.path.join(job_dir, "*.ghl.json")))
    if spec is not None and spec.platform == "gohighlevel" and not ghl_files:
        report.fails.append("no *.ghl.json in the job folder (not compiled/copied)")
    for path in ghl_files:
        name = os.path.basename(path)
        _, raw, error = _load_json(path)
        if error:
            report.fails.append("{}: does not parse ({})".format(name, error))
        if not _is_ascii(raw):
            report.fails.append("{}: non-ASCII character {}".format(name, _first_non_ascii(raw)))
        if "UNRESOLVED" in raw:
            report.fails.append("{}: contains {} UNRESOLVED id(s)".format(
                name, raw.count("UNRESOLVED")))

    # -- proposal + beats --------------------------------------------------
    proposal = read_text(os.path.join(job_dir, "proposal.md"))
    if proposal is None:
        report.fails.append("proposal.md missing")
    else:
        fails, report.preview_len = check_proposal(proposal)
        report.fails.extend(fails)
        preview = preview_of(proposal) or ""
        if RUNTIME_PLACEHOLDER in preview:
            report.notes.append("preview counts {} as 1 char (the runtime digit it becomes)"
                                .format(RUNTIME_PLACEHOLDER))
    beats = read_text(os.path.join(job_dir, "beats.md"))
    if beats is None:
        report.fails.append("beats.md missing")
    else:
        report.fails.extend(check_beats(beats))

    # -- genericness: client + chart clone ---------------------------------
    client = raw_spec.get("client") if isinstance(raw_spec, dict) else None
    if spec is not None and isinstance(client, dict):
        report.warns.extend(lint_client(client, spec.title, workflows, beats or ""))
    if spec is not None and is_chart(spec):
        spec_archetype = raw_spec.get("archetype") if isinstance(raw_spec, dict) else None
        own = own_archetypes(job_dir, spec_archetype if isinstance(spec_archetype, str) else None,
                             vault_dir)
        for archetype_id, matched, total in chart_overlaps(spec, vault_dir):
            if archetype_id in own:
                report.notes.append("chart overlaps {} on {} of {} steps; not a clone: that is "
                                    "this job's own earlier build ({})".format(
                                        archetype_id, matched, total, own[archetype_id]))
                continue
            report.warns.append("lint: chart overlaps {} on {} of {} steps".format(
                archetype_id, matched, total))
    return report


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------


def _table(headers: List[str], rows: List[List[str]]) -> str:
    widths = [max(len(str(r[i])) for r in [headers] + rows) for i in range(len(headers))]
    line = lambda r: "  " + " | ".join(str(c).ljust(w) for c, w in zip(r, widths))  # noqa: E731
    out = [line(headers), "  " + "-+-".join("-" * w for w in widths)]
    out.extend(line(r) for r in rows)
    return "\n".join(out)


def status_of(report: JobReport) -> str:
    if report.fails:
        return "FAIL"
    return "WARN" if report.warns else "ok"


def print_reports(reports: List[JobReport], details: bool = True) -> None:
    rows = [[r.slug, r.platform, str(r.nodes),
             "-" if r.preview_len is None else str(r.preview_len),
             str(len(r.fails)), str(len(r.warns)), status_of(r)] for r in reports]
    print()
    print(_table(["job", "platform", "nodes", "preview", "FAIL", "WARN", "status"], rows))
    if not details:
        return
    for report in reports:
        if not report.fails and not report.warns and not report.notes:
            continue
        print("\n  == {}".format(report.slug))
        for item in report.fails:
            print("    FAIL  {}".format(item))
        for item in report.warns:
            print("    WARN  {}".format(item))
        for item in report.notes:
            print("    note  {}".format(item))
    print()


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="upwork_gen.verify_job", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("jobs", nargs="*", help="job folders")
    parser.add_argument("--order", type=int, metavar="N",
                        help="verify the first N slugs of jobs/_ORDER.txt")
    args = parser.parse_args(argv)

    jobs = list(args.jobs)
    if args.order:
        jobs.extend(order_slugs(args.order))
    if not jobs:
        parser.error("give job folders or --order N")
    missing = [j for j in jobs if not os.path.isdir(j)]
    if missing:
        print("  not a folder: {}".format(", ".join(missing)), file=sys.stderr)
        return 2
    reports = [verify(job) for job in jobs]
    print_reports(reports)
    return 1 if any(r.fails for r in reports) else 0


if __name__ == "__main__":
    sys.exit(main())
