"""Synthesise plausible node parameters, and translate spec shorthand.

A canvas whose node labels promise real work, and whose nodes are empty when
clicked, undercuts the whole pitch — the diagram reads as a mock-up rather than
a build. Node types and versions came from the harvest; full parameter schemas
did not, so these are reconstructed from the shapes n8n uses and are deliberately
conservative: n8n ignores parameters it does not recognise, so a wrong guess
renders a plain node rather than an error.

The two that matter most:

* **Switch** — its outputs are generated from the spec's branch labels, so the
  node shows the real routing (`sales`, `id_card`, `callback`) instead of an
  unconfigured stub. This is the single most convincing node on a canvas.
* **Set** — its field list is generated from the sample payload flowing through
  it, so a "Normalize" node actually lists the fields it normalises.

Spec shorthand
--------------
A spec node's `params` may carry short, readable keys that this module turns
into real n8n parameters (see SHORTHAND_KEYS). Shorthand keys are always
removed, so they never reach the n8n JSON as unknown keys. Every other key in
`params` is a raw n8n parameter and passes through unchanged, over whatever was
synthesised.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
import uuid
from typing import Any, Dict, List, Optional, Set, Tuple

from .spec import (CONFIG_KEY_RE, Edge, Node, WorkflowSpec, declares_error_handler,
                   is_error_trigger)

_NAMESPACE = uuid.UUID("8c2a7d31-55b0-4e7a-9f10-3d6e2b8c4a55")


# --------------------------------------------------------------------------
# ASCII
# --------------------------------------------------------------------------
# Every written file is pure ASCII (generate.write_output). The fold lives
# here so a node reference can be built from the exact name the file carries.

_ASCII_SWAPS = {"\u00b7": "-", "\u2014": "-", "\u2013": "-", "\u2019": "'",
                "\u201c": '"', "\u201d": '"', "\u2192": "->", "\u2265": ">=",
                "\u2264": "<=", "\u2194": "-", "\u2190": "-", "\u2026": "...",
                "\u00d7": "x", "\u2713": "OK", "\u2714": "OK"}
# Two-way and back arrows read as a spaced dash: "CRM <-> Airtable" becomes
# "CRM - Airtable", never "CRM  Airtable".
_SPACED_DASH = re.compile("[ \t]*[\u2194\u2190][ \t]*")
# Whatever is still not ASCII and sits between two words becomes one space.
_BETWEEN_WORDS = re.compile(r"(?<=\S)[ \t]*[^\x00-\x7f]+[ \t]*(?=\S)")


def _fold(char: str) -> str:
    """An accented letter keeps its base letter ("e" for "e-acute")."""
    base = unicodedata.normalize("NFKD", char).encode("ascii", "ignore").decode("ascii")
    return base if base.isalnum() else char


def ascii_safe(text: str) -> str:
    text = _SPACED_DASH.sub(" - ", text)
    for src, dst in _ASCII_SWAPS.items():
        text = text.replace(src, dst)
    text = re.sub(r"[^\x00-\x7f]", lambda m: _fold(m.group(0)), text)
    text = _BETWEEN_WORDS.sub(" ", text)
    return text.encode("ascii", "ignore").decode("ascii")


def ascii_safe_obj(value: Any) -> Any:
    """ascii_safe on every string in a JSON value, dict keys included.

    Folding happens before serialising, never on serialised text: a curly
    double quote becomes `"` inside its own string, which json.dumps then
    escapes, instead of ending the string early and breaking the file.
    """
    if isinstance(value, str):
        return ascii_safe(value)
    if isinstance(value, dict):
        return {(ascii_safe(k) if isinstance(k, str) else k): ascii_safe_obj(v)
                for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [ascii_safe_obj(v) for v in value]
    return value


def _dumps(value: Any) -> str:
    """JSON text embedded in a parameter (a schema, a body). Folded first, so
    the file-level fold never has to touch serialised text."""
    return json.dumps(ascii_safe_obj(value), indent=2, ensure_ascii=False)


def node_ref(name: str) -> str:
    """`$('<name>')` for one node, as the written file will carry it.

    The name is folded exactly as the node's own name is on write, then a
    backslash or apostrophe is escaped, so "Owner's" (straight or curly)
    reads `$('Owner\\'s')` and never ends the string early.
    """
    text = ascii_safe(name).replace("\\", "\\\\").replace("'", "\\'")
    return "$('{}')".format(text)


_CONDITION_OPTIONS = {
    "caseSensitive": True,
    "leftValue": "",
    "typeValidation": "strict",
    "version": 2,
}

# The one Set node the compiler inserts when a spec has `config` (never more
# than one per workflow; see compile_n8n.with_config_node for where it goes).
# Other nodes reference it by this exact name.
CONFIG_NODE_KEY = "__config"
CONFIG_NODE_NAME = "0 - Config: Your Settings"


def is_config_node(node: Optional[Node]) -> bool:
    return node is not None and node.key == CONFIG_NODE_KEY


def placeholder_value(key: str) -> str:
    """What a client-set value reads until they fill it in:
    `ghl_api_key` -> `PASTE-YOUR-GHL-API-KEY`."""
    return "PASTE-YOUR-" + re.sub(r"[^A-Z0-9]+", "-", str(key).upper()).strip("-")

_SERVICES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "catalog", "http_services.json")

_STEP_PREFIX = re.compile(r"^\s*\d+[a-z]?\s*[·.:-]\s*")

# The catalog's own placeholder parser schema. It must never survive into a
# workflow when the spec has a real sample to derive one from.
DEFAULT_PARSER_EXAMPLE = {"summary": "text", "score": 1}


def _cid(*parts: str) -> str:
    return str(uuid.uuid5(_NAMESPACE, "::".join(parts)))


def strip_step(label: str) -> str:
    """"3b - GHL: Tag Contact" -> "GHL: Tag Contact"."""
    return _STEP_PREFIX.sub("", label or "").strip()


def _guess_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, (list, tuple)):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "string"


def _numeric_hint(label: str) -> Optional[float]:
    """Pull a threshold out of a label like "Score ≥ 70?" so the condition on
    the canvas matches what the node is called. The step prefix ("3 - ") is
    stripped first, or every gate would read its own step number."""
    bare = re.sub(r"^\s*\d+[a-z]?\s*[·.:-]\s*", "", label)
    match = re.search(r"(\d+(?:\.\d+)?)", bare)
    return float(match.group(1)) if match else None


# Interrogatives and auxiliaries lead most condition labels ("What They Need",
# "During Business Hours?") and are useless as field names.
_LABEL_SKIP = {
    "the", "is", "are", "was", "were", "be", "to", "a", "an", "and", "or", "of", "in",
    "for", "on", "at", "by", "with", "from", "what", "when", "where", "which", "who",
    "why", "how", "does", "do", "did", "has", "have", "had", "can", "could", "should",
    "will", "would", "if", "then", "else", "any", "all", "during", "over", "under",
    "above", "below", "they", "it", "this", "that", "we", "our", "your", "more", "than",
}


def _label_words(label: str) -> List[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9]+", label)
    return [w.lower() for w in words if w.lower() not in _LABEL_SKIP]


def _bare_words(label: str) -> List[str]:
    return _label_words(strip_step(label))


def _stem(word: str) -> str:
    word = word.lower()
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


# Verbs that lead step labels ("Check the Log", "Send the Reply"). They name
# what a step does, not a field, so they may match a whole key but never one
# part of it: "check" is not `check_in_date`, "send" is not `send_at`.
GENERIC_VERBS = {"check", "get", "set", "update", "make", "run", "work", "send", "create",
                 "add", "build"}


def _key_matches(word: str, key: str) -> bool:
    """Whether a label word names a field: `email` names `email`, `class`
    names `lead_class`, `fields` names `missing_fields`."""
    if len(word) < 3:
        return False
    word = _stem(word)
    key = key.lower()
    if word == _stem(key):
        return True
    if word in GENERIC_VERBS or word.lower() in GENERIC_VERBS:
        return False
    return any(word == _stem(part) for part in key.split("_") if part)


# --------------------------------------------------------------------------
# Sample helpers
# --------------------------------------------------------------------------


def _as_dict(sample: Any) -> Dict[str, Any]:
    if isinstance(sample, dict):
        return sample
    if isinstance(sample, list) and sample and isinstance(sample[0], dict):
        return sample[0]
    return {}


def _leaf_keys(sample: Any, depth: int = 3) -> List[str]:
    """Every key name in a sample, nested ones included, in order."""
    out: List[str] = []

    def visit(value: Any, level: int) -> None:
        if level > depth:
            return
        if isinstance(value, dict):
            for key, inner in value.items():
                out.append(str(key))
                visit(inner, level + 1)
        elif isinstance(value, list) and value and isinstance(value[0], dict):
            visit(value[0], level + 1)

    visit(sample, 0)
    return out


def _all_keys(spec: Optional[WorkflowSpec]) -> List[str]:
    if spec is None:
        return []
    keys: List[str] = []
    for key in _leaf_keys(spec.input_sample) + _leaf_keys(spec.output_sample):
        if key not in keys:
            keys.append(key)
    return keys


def _resolve_field(name: str, spec: Optional[WorkflowSpec]) -> str:
    """The sample's own spelling of a field: `contact_id` -> `ghl_contact_id`
    when that is what the payload calls it. Falls back to the name as given."""
    keys = _all_keys(spec)
    if name in keys:
        return name
    for key in keys:
        if key.lower().endswith("_" + name.lower()):
            return key
    return name


def _scalar_keys(sample: Any) -> List[str]:
    return [str(k) for k, v in _as_dict(sample).items() if not isinstance(v, (dict, list))]


_LONG_TEXT = ("message", "body", "text", "notes", "note", "description", "transcript",
              "content", "summary", "details", "comment", "question", "request")


def _pretty(key: str) -> str:
    return key.replace("_", " ").strip().capitalize()


def _best_sample_dict(words: List[str], sample: Any) -> Tuple[Dict[str, Any], int]:
    """The nested object in `sample` whose keys the words describe best.

    "Service, Summary, Class, Missing Fields" lands on the `qualification`
    object rather than the whole payload, which is what that step produces.
    Returns ({}, 0) when nothing nested scores.
    """
    best: Dict[str, Any] = {}
    best_score = 0

    def score(obj: Dict[str, Any], name: str) -> int:
        points = sum(1 for key in obj if any(_key_matches(w, str(key)) for w in words))
        if name and any(_key_matches(w, name) for w in words):
            points += 2
        return points

    def visit(obj: Any, name: str, level: int) -> None:
        nonlocal best, best_score
        if level > 2 or not isinstance(obj, dict):
            return
        if level > 0:
            points = score(obj, name)
            if points > best_score:
                best, best_score = obj, points
        for key, value in obj.items():
            if isinstance(value, dict):
                visit(value, str(key), level + 1)

    visit(_as_dict(sample), "", 0)
    return best, best_score


def _all_ancestors(spec: WorkflowSpec, key: str) -> List[Node]:
    """Every upstream flow node, nearest first, Config nodes included."""
    seen: Set[str] = set()
    out: List[Node] = []
    frontier = [e.src for e in spec.predecessors(key)]
    while frontier:
        current = frontier.pop(0)
        if current in seen:
            continue
        seen.add(current)
        try:
            out.append(spec.node(current))
        except Exception:
            continue
        frontier.extend(e.src for e in spec.predecessors(current))
    return out


def _ancestors(spec: WorkflowSpec, key: str) -> List[Node]:
    """Upstream nodes that carry business data. A Config node only holds
    settings, so it is walked through but never returned: field lookups,
    "first Set on the path" and AI read-backs all skip it."""
    return [n for n in _all_ancestors(spec, key) if not is_config_node(n)]


def _first_predecessor(spec: WorkflowSpec, key: str) -> Optional[Node]:
    """The node feeding this one, looking through a Config node to the node
    before it."""
    hops = 0
    while hops < 8:
        edges = spec.predecessors(key)
        if not edges:
            return None
        try:
            node = spec.node(edges[0].src)
        except Exception:
            return None
        if not is_config_node(node):
            return node
        key = node.key
        hops += 1
    return None


def _on_error_path(node: Node, spec: WorkflowSpec) -> bool:
    return any(is_error_trigger(a) for a in _ancestors(spec, node.key))


_PASS_THROUGH = {"flow.branch", "flow.switch", "data.filter", "flow.wait", "flow.noop"}


def _producer(node: Node, spec: WorkflowSpec) -> Optional[Node]:
    """The nearest upstream node whose output this node actually receives:
    If, Switch, Filter and Wait hand their input on unchanged."""
    current = _first_predecessor(spec, node.key)
    hops = 0
    while current is not None and current.kind in _PASS_THROUGH and hops < 12:
        current = _first_predecessor(spec, current.key)
        hops += 1
    return current


def node_names(spec: WorkflowSpec) -> Dict[str, str]:
    from .spec import unique_names
    return unique_names([(n.key, n.label) for n in spec.nodes])


def payload_source(node: Node, spec: WorkflowSpec, producer: Node) -> Optional[Node]:
    """Where a node after an AI step reads the original payload back from.

    Only a node that runs on every path into this node qualifies (the rule
    config_source uses): n8n throws "Referenced node is unexecuted" for one
    that did not run, so a Set on one branch, or one of several triggers,
    never does. Nearest first: a Set or trigger above `producer`; where none
    runs on every path (several triggers meeting), the Merge that joins them,
    or an If/Switch/Filter/Wait that hands a trigger, Set or Merge output on
    unchanged. None when nothing qualifies; the caller then reads the
    incoming item.
    """
    anchor = _flow_anchor(node, spec)
    if anchor is None:
        return None
    above = [a for a in _ancestors(spec, producer.key)
             if _dominates(spec, a.key, anchor.key)]
    for source in above:
        if source.kind == "data.transform" or source.is_trigger:
            return source
    for source in above:
        if source.kind == "data.merge":
            return source
        if source.kind in _PASS_THROUGH:
            fed_by = _producer(source, spec)
            if fed_by is not None and (fed_by.is_trigger or fed_by.kind in (
                    "data.transform", "data.merge")):
                return source
    return None


def field_ref(node: Node, spec: Optional[WorkflowSpec], name: str) -> str:
    """Expression body for a field as this node would really read it.

    After an AI step the item is the model's output, so its own fields read
    `$json.output.<key>` and anything from the original payload is read back
    from the step that last held it, `$('2 - Tidy ...').item.json.<key>`,
    when that step runs on every path into this node (payload_source); else
    from the incoming item, `$json.<key>`, which never fails.
    After a known API call, an id reads from where that API returns it.
    """
    key = _resolve_field(name, spec)
    if spec is None or node is None:
        return "$json." + key
    producer = _producer(node, spec)
    if producer is None:
        return "$json." + key
    if producer.kind in ("ai.llm", "ai.agent"):
        ai_keys = _ai_output_keys(producer, spec)
        if key in ai_keys or name in ai_keys:
            return "$json.output." + (key if key in ai_keys else name)
        source = payload_source(node, spec, producer)
        if source is not None:
            label = node_names(spec).get(source.key, source.label)
            return "{}.item.json.{}".format(node_ref(label), key)
        return "$json." + key
    found = resolve_service(producer, spec) if producer.kind in ("net.http", "app.action") \
        else None
    if found and name.endswith("id"):
        id_path = found[3].get("id_path") or ""
        head = id_path.split(".")[0]
        if head and (name.startswith(head) or key.endswith(head + "_id")):
            return "$json." + id_path
    return "$json." + key


# --------------------------------------------------------------------------
# Config references
# --------------------------------------------------------------------------


def has_config(spec: Optional[WorkflowSpec]) -> bool:
    """Whether the spec has a Config node wired in (not merely a `config`
    block): only then can anything reference one."""
    return bool(spec is not None and any(is_config_node(n) for n in spec.nodes))


def _json_access(key: str) -> str:
    """`.key` for a plain identifier, `["Booking Link"]` otherwise, so a
    badly named setting still yields a valid expression."""
    if CONFIG_KEY_RE.match(key) or re.match(r"^[A-Za-z_$][A-Za-z0-9_$]*$", key):
        return "." + key
    return "[{}]".format(json.dumps(key))


def config_ref(key: str, config_name: str = CONFIG_NODE_NAME) -> str:
    """The expression body (no braces) that reads one Config setting."""
    return "{}.item.json{}".format(node_ref(config_name), _json_access(key))


# `$('0 - Config: Your Settings')` as a spec author writes it into a param by
# hand, then the Config item's json (`.item.json`, `.first().json`,
# `.last().json`).
_CONFIG_CALL = r"\$\(\s*(?P<quote>['\"]){}(?P=quote)\s*\)".format(
    re.escape(CONFIG_NODE_NAME))
_CONFIG_JSON = _CONFIG_CALL + r"\s*\.\s*(?:item|first\(\s*\)|last\(\s*\))\s*\.\s*json"
# `.key` or `['key']` / `["key"]` after the json (or after a bound variable).
_KEY_ACCESS = r"(?:\.\s*([A-Za-z_$][A-Za-z0-9_$]*)|\[\s*(['\"])(.+?)\{q}\s*\])"
_CONFIG_READ_RE = re.compile(_CONFIG_JSON + _KEY_ACCESS.format(q=3))
# `const cfg = $('0 - Config: Your Settings').first().json;` binds the whole
# json, so `cfg.key` reads further on in the same string are Config reads too.
_CONFIG_BIND_RE = re.compile(r"\b(?:const|let|var)\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*"
                             + _CONFIG_JSON + r"(?!\s*(?:\.|\[))")
_CONFIG_NAMED_RE = re.compile(_CONFIG_CALL)


def _param_strings(value: Any) -> List[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        value = list(value.values())
    if isinstance(value, list):
        return [text for item in value for text in _param_strings(item)]
    return []


def config_keys_read(spec: WorkflowSpec) -> Optional[List[str]]:
    """The Config keys the spec's own node params read by name, first seen
    first; None when no param names the Config node at all (an empty list
    when one does without a key that can be told).

    A vault archetype has its `config` stripped on promotion but keeps any
    `$('0 - Config: Your Settings').item.json.key` its author wrote, so the
    compiler needs these keys to build the node those params point at.
    """
    keys: List[str] = []
    named = False
    for node in spec.nodes:
        for text in _param_strings(node.params):
            if not _CONFIG_NAMED_RE.search(text):
                continue
            named = True
            found = [(m.start(), m.group(2) or m.group(4))
                     for m in _CONFIG_READ_RE.finditer(text)]
            for bind in _CONFIG_BIND_RE.finditer(text):
                var = re.compile(r"(?<![A-Za-z0-9_$.])" + re.escape(bind.group(1)) + r"\s*"
                                 + _KEY_ACCESS.format(q=2))
                found.extend((m.start(), m.group(1) or m.group(3))
                             for m in var.finditer(text, bind.end()))
            for _, key in sorted(found):
                if key not in keys:
                    keys.append(key)
    return keys if named else None


def _flow_anchor(node: Node, spec: WorkflowSpec) -> Optional[Node]:
    """The main-graph node an AI sub-node ultimately hangs off."""
    hops = 0
    while node is not None and node.is_ai_sub and node.parent and hops < 6:
        try:
            node = spec.node(node.parent)
        except Exception:
            return None
        hops += 1
    return node


def _dominates(spec: WorkflowSpec, gate: str, target: str) -> bool:
    """Whether every path from a root of the graph to `target` runs through
    `gate`, so `gate` has always executed by the time `target` does."""
    roots = [n.key for n in spec.flow_nodes if not spec.predecessors(n.key)]
    seen: Set[str] = set()
    frontier = [r for r in roots if r != gate]
    while frontier:
        current = frontier.pop()
        if current in seen:
            continue
        seen.add(current)
        if current == target:
            return False
        frontier.extend(e.dst for e in spec.successors(current) if e.dst != gate)
    return True


def config_source(node: Optional[Node], spec: Optional[WorkflowSpec]) -> Optional[Node]:
    """The Config node, when every path into this node passes through it.
    None otherwise (another trigger path, the error path, a node before it,
    or a spec without config); callers then write the literal placeholder."""
    if node is None or spec is None or not has_config(spec):
        return None
    anchor = _flow_anchor(node, spec)
    if anchor is None:
        return None
    for candidate in _all_ancestors(spec, anchor.key):
        if is_config_node(candidate) and _dominates(spec, candidate.key, anchor.key):
            return candidate
    return None


def config_expr(node: Optional[Node], spec: Optional[WorkflowSpec], key: str
                ) -> Optional[str]:
    """`$('<its Config node>').item.json.<key>` for this node, or None when
    no Config node is upstream of it."""
    source = config_source(node, spec)
    if source is None:
        return None
    return config_ref(key, node_names(spec).get(source.key, source.label))


# --------------------------------------------------------------------------
# Conditions
# --------------------------------------------------------------------------


def _field_hint(node: Node, spec: Optional[WorkflowSpec] = None,
                default: str = "status") -> str:
    """A field name for a condition, grounded in the sample data where possible.

    Preferring a key that actually exists in the payload is what makes the
    expression read as though it was written against real data rather than
    invented — `$json.fit_score` instead of `$json.score`.
    """
    words = _label_words(node.label)

    if spec is not None:
        keys: List[str] = []
        for sample in (spec.input_sample, spec.output_sample):
            if isinstance(sample, dict):
                keys.extend(str(k) for k in sample)
        for word in words:
            for key in keys:
                parts = key.lower().split("_")
                if word == key.lower() or (word in parts and word not in GENERIC_VERBS):
                    return key

    if not words:
        return default
    # Two words make a better field name than one: "Meets Standard?" reads as
    # meets_standard, which is what such a field would actually be called.
    return "_".join(words[:2])


def _matches_sample(node: Node, spec: Optional[WorkflowSpec]) -> bool:
    """Whether the label named a field that genuinely exists in the payload."""
    if spec is None:
        return False
    keys = []
    for sample in (spec.input_sample, spec.output_sample):
        if isinstance(sample, dict):
            keys.extend(str(k).lower() for k in sample)
    for word in _label_words(node.label):
        if any(word == k or (word in k.split("_") and word not in GENERIC_VERBS)
               for k in keys):
            return True
    return False


_UNARY_OPS = {"exists", "notExists", "empty", "notEmpty", "true", "false"}


def _condition(node: Node, left: str, right: Any, operation: str, kind: str,
               salt: str = "") -> Dict[str, Any]:
    operator: Dict[str, Any] = {"type": kind, "operation": operation}
    if operation in _UNARY_OPS:
        operator["singleValue"] = True
        right = ""
    return {
        "id": _cid(node.key, str(right), operation, salt) if salt else
              _cid(node.key, str(right), operation),
        "leftValue": left,
        "rightValue": right,
        "operator": operator,
    }


def _condition_block(conditions: List[Dict[str, Any]],
                     combinator: str = "and") -> Dict[str, Any]:
    return {
        "options": dict(_CONDITION_OPTIONS),
        "conditions": conditions,
        "combinator": combinator,
    }


# Shorthand op -> (n8n operator type or None to infer from the right value, operation).
_SHORT_OPS = {
    "gte": ("number", "gte"), ">=": ("number", "gte"),
    "gt": ("number", "gt"), ">": ("number", "gt"),
    "lte": ("number", "lte"), "<=": ("number", "lte"),
    "lt": ("number", "lt"), "<": ("number", "lt"),
    "eq": (None, "equals"), "==": (None, "equals"), "equals": (None, "equals"),
    "neq": (None, "notEquals"), "!=": (None, "notEquals"),
    "contains": ("string", "contains"),
    "exists": ("string", "exists"), "not_exists": ("string", "notExists"),
    "empty": ("string", "empty"), "not_empty": ("string", "notEmpty"),
    "true": ("boolean", "true"), "false": ("boolean", "false"),
}

SHORTHAND_CONDITION_OPS = ("gte", "gt", "lte", "lt", "eq", "neq", "contains",
                           "exists", "true", "false")


def _expr(left: Any) -> str:
    """Normalise a left-hand side to an n8n expression string."""
    text = str(left).strip()
    if text.startswith("="):
        return text
    if "{{" in text:
        return "=" + text
    if text.startswith("$"):
        return "={{ %s }}" % text
    return "={{ $json.%s }}" % text


def _short_condition(node: Node, raw: Any, index: int) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, dict) or "left" not in raw:
        return None
    op = str(raw.get("op", "eq")).strip()
    kind, operation = _SHORT_OPS.get(op, _SHORT_OPS.get(op.lower(), (None, "equals")))
    right = raw.get("right", "")
    if kind == "number" and isinstance(right, str):
        try:
            right = float(right) if "." in right else int(right)
        except ValueError:
            pass
    if kind is None:
        kind = _guess_type(right)
        if kind not in ("number", "boolean"):
            kind = "string"
    return _condition(node, _expr(raw["left"]), right, operation, kind, salt=str(index))


def shorthand_conditions(node: Node, raw: Any) -> Optional[Dict[str, Any]]:
    """`condition` shorthand -> an If/Filter v2 `conditions` block.

    Accepts one {"left", "op", "right"} object or a list of them (combined
    with AND). Returns None when the value is not in that shape.
    """
    items = raw if isinstance(raw, list) else [raw]
    built = [c for c in (_short_condition(node, item, i) for i, item in enumerate(items)) if c]
    if not built:
        return None
    return _condition_block(built)


_PRESENCE_WORDS = {"present", "complete", "completed", "required", "filled", "provided",
                   "valid", "enough"}
_EXIST_WORDS = {"exists", "exist", "existing", "already", "found", "duplicate", "known",
                "returning", "matched", "match", "seen"}
_CLARITY_WORDS = {"clear", "confident", "sure", "certain", "qualify", "qualified",
                  "understood"}
_CLASS_KEYS = ("class", "category", "classification", "intent", "label", "tier",
               "status", "type", "segment")
_IDENTITY_KEYS = ("name", "first_name", "full_name", "email", "phone", "company",
                  "company_name", "message")


def _ai_output_keys(node: Optional[Node], spec: WorkflowSpec) -> Dict[str, Any]:
    """The structured fields an AI step returns, when it has a parser."""
    if node is None or node.kind not in ("ai.llm", "ai.agent"):
        return {}
    for child in spec.children_of(node.key):
        if child.kind == "ai.parser":
            example = parser_example(child, spec)
            return example if isinstance(example, dict) else {}
    return {}


def _service_id_path(node: Optional[Node], spec: WorkflowSpec) -> Optional[str]:
    if node is None:
        return None
    found = resolve_service(node, spec)
    if not found:
        return None
    return found[3].get("id_path")


def _default_conditions(node: Node, spec: WorkflowSpec) -> Dict[str, Any]:
    """An If condition that reads its label against the real payload."""
    words = _bare_words(node.label)
    label = strip_step(node.label).lower()
    pred = _first_predecessor(spec, node.key)
    ai_keys = _ai_output_keys(pred, spec)
    ai_prefix = "$json.output."

    # 1. A number in the label is a threshold.
    threshold = _numeric_hint(node.label)
    if threshold is not None:
        field = None
        for key in ai_keys:
            if any(_key_matches(w, key) for w in words):
                field = ai_prefix + key
                break
        if field is None:
            for key in ai_keys:
                if any(t in key for t in ("score", "confidence", "probability")):
                    field = ai_prefix + key
                    break
        if field is None:
            field = "$json." + _field_hint(node, spec, default="status")
        return _condition_block([
            _condition(node, "={{ %s }}" % field, threshold, "gte", "number")])

    # 2. A label word that is one of the sample's own values: "Hot Lead?".
    value_sources: List[Tuple[str, Dict[str, Any]]] = []
    if ai_keys:
        value_sources.append((ai_prefix, ai_keys))
    for sample in (spec.input_sample, spec.output_sample):
        value_sources.append(("$json.", _as_dict(sample)))
    for prefix, sample in value_sources:
        for key, value in sample.items():
            if isinstance(value, str) and 2 < len(value) < 30 and \
                    value.lower() in words and key.lower() not in words:
                return _condition_block([_condition(
                    node, "={{ %s%s }}" % (prefix, key), value, "equals", "string")])

    # 3. A real boolean field the label names.
    for prefix, sample in value_sources:
        for key, value in sample.items():
            if isinstance(value, bool) and any(_key_matches(w, key) for w in words):
                return _condition_block([_condition(
                    node, "={{ %s%s }}" % (prefix, key), True, "true", "boolean")])

    # 4. "Already Exists?" — does the lookup before it return a record?
    if set(words) & _EXIST_WORDS:
        id_path = _service_id_path(pred, spec)
        if id_path:
            left = "$json." + id_path
        else:
            candidates = [k for k in _all_keys(spec) if k.lower() == "id" or
                          k.lower().endswith("_id")]
            pred_words = _bare_words(pred.label) if pred else []
            chosen = None
            for key in candidates:
                if any(_key_matches(w, key) for w in words + pred_words):
                    chosen = key
                    break
            left = "$json." + (chosen or (candidates[0] if candidates else "id"))
        return _condition_block([_condition(node, "={{ %s }}" % left, "", "exists", "string")])

    # 5. "Required Fields Present?" — the fields the rest of the flow needs.
    if set(words) & _PRESENCE_WORDS and not (set(words) & _CLARITY_WORDS):
        sample = _as_dict(spec.input_sample)
        named = [k for k in sample if any(_key_matches(w, k) for w in words)]
        fields = named or [k for k in _IDENTITY_KEYS if k in sample][:3] or \
            _scalar_keys(sample)[:2]
        if fields:
            return _condition_block([
                _condition(node, "={{ $json.%s }}" % k, "", "notEmpty", "string", salt=k)
                for k in fields[:3]])

    # 6. "Clear Enough to Qualify?" after an AI step: confidence, else class.
    if ai_keys and set(words) & (_CLARITY_WORDS | {"enough"}):
        for key in ai_keys:
            if any(t in key.lower() for t in ("confidence", "certainty", "probability")):
                return _condition_block([_condition(
                    node, "={{ %s%s }}" % (ai_prefix, key), 0.7, "gte", "number")])
        for key in ai_keys:
            if any(key.lower() == c or key.lower().endswith("_" + c) for c in _CLASS_KEYS):
                unclear = "unclear"
                parent_label = (pred.label if pred else "").lower()
                if "unknown" in parent_label and "unclear" not in parent_label:
                    unclear = "unknown"
                return _condition_block([_condition(
                    node, "={{ %s%s }}" % (ai_prefix, key), unclear, "notEquals", "string")])

    # 7. Any yes/no field the AI step returns.
    for key, value in ai_keys.items():
        if isinstance(value, bool):
            return _condition_block([_condition(
                node, "={{ %s%s }}" % (ai_prefix, key), True, "true", "boolean")])

    # 8. The label names a real field: test that it is set.
    for prefix, sample in value_sources:
        for key in sample:
            if any(_key_matches(w, str(key)) for w in words):
                return _condition_block([_condition(
                    node, "={{ %s%s }}" % (prefix, key), "", "notEmpty", "string")])

    # 9. Nothing to ground it on.
    field = _field_hint(node, spec, default="status")
    return _condition_block([
        _condition(node, "={{ $json.%s }}" % field, True, "true", "boolean")])


def for_branch(node: Node, spec: Optional[WorkflowSpec] = None,
               short: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """An If node whose condition reflects the question in its label."""
    short = short or {}
    block = shorthand_conditions(node, short.get("condition")) if "condition" in short else None
    if block is None and spec is not None:
        block = _default_conditions(node, spec)
    if block is None:
        field = _field_hint(node, spec, default="status")
        threshold = _numeric_hint(node.label)
        if threshold is not None:
            block = _condition_block([_condition(
                node, "={{ $json.%s }}" % field, threshold, "gte", "number")])
        else:
            block = _condition_block([_condition(
                node, "={{ $json.%s }}" % field, True, "true", "boolean")])
    return {"conditions": block, "options": {}}


def for_switch(node: Node, edges: List[Edge],
               spec: Optional[WorkflowSpec] = None) -> Dict[str, Any]:
    """A Switch whose outputs are the spec's own branch labels.

    Without this the node renders as a single unconfigured output and the fan-out
    on the canvas looks like it came from nowhere.
    """
    # A router keys off an intent field; that is what such a field is called,
    # and the label ("What They Need") rarely names it.
    field = _field_hint(node, spec, default="intent")
    if field == "_".join(_label_words(node.label)[:2]) and not _matches_sample(node, spec):
        field = "intent"
    values: List[Dict[str, Any]] = []
    for edge in edges:
        label = (edge.branch or "default").strip()
        values.append({
            "conditions": _condition_block([
                _condition(node, "={{ $json.%s }}" % field, label, "equals", "string")
            ]),
            "renameOutput": True,
            "outputKey": label,
        })
    return {"rules": {"values": values}, "options": {}}


# --------------------------------------------------------------------------
# AI nodes
# --------------------------------------------------------------------------


def _first_sentences(text: str, count: int = 2) -> str:
    parts = re.split(r"(?<=[.!?])\s+", (text or "").strip())
    return " ".join(p for p in parts[:count] if p).strip()


def _section_note(node: Node, spec: WorkflowSpec) -> str:
    for section in spec.sections:
        if section.key == node.section:
            return section.note or ""
    return ""


def _chat_driven(node: Node, spec: WorkflowSpec) -> bool:
    return any(a.kind == "trigger.chat" for a in _ancestors(spec, node.key))


def _prompt_fields(spec: WorkflowSpec, limit: int = 8) -> Tuple[List[str], List[str]]:
    """(short fields, long-text fields) from the input sample."""
    short: List[str] = []
    long: List[str] = []
    for key in _scalar_keys(spec.input_sample):
        if any(t == key.lower() or key.lower().endswith("_" + t) for t in _LONG_TEXT):
            long.append(key)
        else:
            short.append(key)
    return short[:limit], long[:2]


def synth_prompt(node: Node, spec: WorkflowSpec) -> str:
    """A prompt that hands the model the real fields, labelled."""
    short, long = _prompt_fields(spec)
    if not short and not long:
        return "={{ JSON.stringify($json, null, 2) }}"
    lines = ["Details for this step:"]
    for key in short:
        lines.append("- {}: {{{{ $json.{} }}}}".format(_pretty(key), key))
    for key in long:
        lines.append("")
        lines.append("{}:".format(_pretty(key)))
        lines.append("{{{{ $json.{} }}}}".format(key))
    return "=" + "\n".join(lines)


def synth_system_message(node: Node, spec: WorkflowSpec,
                         output_keys: Optional[List[str]] = None) -> str:
    """Who the model works for, what this step is for, and what it returns."""
    who = spec.client.get("company") or spec.client.get("name")
    parts: List[str] = []
    if who:
        parts.append("You work for {}.".format(who))
    else:
        parts.append("You are one step in the {} workflow.".format(spec.title.strip()))
    note = _first_sentences(_section_note(node, spec), 2)
    if note:
        parts.append(note)
    job = strip_step(node.label).rstrip(" .?!")
    parts.append("Your job in this step: {}.".format(job))
    if output_keys:
        parts.append("Return JSON with exactly these fields: {}.".format(", ".join(output_keys)))
    else:
        parts.append("Return only the result, written so the next step can use it as-is.")
    parts.append("Use only facts in the input. If something is missing, say so instead "
                 "of guessing.")
    return " ".join(parts)


def _parser_keys(node: Node, spec: WorkflowSpec) -> List[str]:
    return list(_ai_output_keys(node, spec).keys())


def for_llm(node: Node, spec: Optional[WorkflowSpec] = None,
            short: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """A chain node shows its prompt and its instructions. An LLM node with no
    visible prompt is the emptiest-looking node on a canvas."""
    short = short or {}
    if spec is None:
        return {"promptType": "define", "text": "={}".format(node.label), "batching": {}}
    prompt = short.get("prompt")
    system = short.get("system_message")
    params: Dict[str, Any] = {"batching": {}}
    if prompt:
        params["promptType"] = "define"
        params["text"] = _as_expression(prompt)
    elif not _chat_driven(node, spec):
        params["promptType"] = "define"
        params["text"] = synth_prompt(node, spec)
    message = system or synth_system_message(node, spec, _parser_keys(node, spec))
    params["messages"] = {"messageValues": [{"message": message}]}
    return params


def for_agent(node: Node, spec: WorkflowSpec,
              short: Optional[Dict[str, Any]] = None,
              base: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """An agent with a system message written for this client and this step."""
    short = short or {}
    params: Dict[str, Any] = {}
    prompt = short.get("prompt")
    if prompt:
        params["promptType"] = "define"
        params["text"] = _as_expression(prompt)
    elif not _chat_driven(node, spec):
        params["promptType"] = "define"
        params["text"] = synth_prompt(node, spec)
    options = dict((base or {}).get("options") or {})
    options["systemMessage"] = short.get("system_message") or \
        synth_system_message(node, spec, _parser_keys(node, spec))
    params["options"] = options
    return params


def _as_expression(text: Any) -> str:
    text = str(text)
    if text.startswith("="):
        return text
    return "=" + text


def is_json_schema(value: Any) -> bool:
    """A real JSON Schema ({"type": "object", "properties": {...}}) rather
    than an example object."""
    return isinstance(value, dict) and value.get("type") == "object" and \
        isinstance(value.get("properties"), dict)


def _parse_schema_text(raw: Any) -> Optional[Dict[str, Any]]:
    if isinstance(raw, dict):
        return raw if is_json_schema(raw) else None
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        parsed = json.loads(raw.lstrip("=").strip())
    except ValueError:
        return None
    return parsed if is_json_schema(parsed) else None


def example_from_schema(schema: Dict[str, Any], depth: int = 0) -> Dict[str, Any]:
    """An example object with one entry per `properties` key, in order."""
    out: Dict[str, Any] = {}
    for key, prop in (schema.get("properties") or {}).items():
        prop = prop if isinstance(prop, dict) else {}
        kind = prop.get("type")
        if isinstance(kind, list):
            kind = next((k for k in kind if k != "null"), "string")
        if "example" in prop:
            value: Any = prop["example"]
        elif isinstance(prop.get("enum"), list) and prop["enum"]:
            value = prop["enum"][0]
        elif kind == "object" and depth < 3:
            value = example_from_schema(prop, depth + 1)
        elif kind == "array":
            value = []
        elif kind in ("number", "integer"):
            value = 0
        elif kind == "boolean":
            value = False
        else:
            value = "text"
        out[str(key)] = value
    return out


def parser_example(node: Node, spec: WorkflowSpec) -> Optional[Dict[str, Any]]:
    """The example object a structured parser should show.

    Order: the node's raw `jsonSchemaExample`, its raw `inputSchema` (read
    from its `properties`), its `schema` shorthand (an example object, or a
    JSON Schema read the same way), the nested object in output_sample that
    the parser's (and its parent's) label describes, the output_sample keys
    the labels name, else the output_sample itself. None only when the spec
    has no output sample at all.
    """
    params = node.params or {}
    raw = params.get("jsonSchemaExample")
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw.lstrip("=").strip())
            if isinstance(parsed, dict):
                return parsed
        except ValueError:
            pass
    for candidate in (params.get("inputSchema"), params.get("schema")):
        schema = _parse_schema_text(candidate)
        if schema is not None:
            return example_from_schema(schema)
    schema = params.get("schema")
    if isinstance(schema, dict) and schema:
        return schema
    sample = _as_dict(spec.output_sample)
    if not sample:
        return None
    words = _bare_words(node.label)
    if node.parent:
        try:
            words += _bare_words(spec.node(node.parent).label)
        except Exception:
            pass
    nested, nested_score = _best_sample_dict(words, sample)
    top = [k for k in sample if any(_key_matches(w, str(k)) for w in words)]
    if nested and nested_score >= 2 and nested_score >= len(top):
        return dict(nested)
    if len(top) >= 2:
        return {k: sample[k] for k in top}
    return {k: sample[k] for k in list(sample)[:8]}


def for_parser(node: Node, spec: WorkflowSpec,
               short: Optional[Dict[str, Any]] = None,
               base: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """A structured parser. A `schema` shorthand that is a JSON Schema goes
    in as n8n's manual schema; anything else shows as a JSON example."""
    short = short or {}
    schema = _parse_schema_text(short.get("schema"))
    if schema is not None:
        return {"schemaType": "manual", "inputSchema": _dumps(schema)}
    example = parser_example(node, spec)
    if example is None:
        return {}
    return {"schemaType": "fromJson", "jsonSchemaExample": _dumps(example)}


def for_memory(node: Node) -> Dict[str, Any]:
    window = _numeric_hint(node.label)
    return {"sessionIdType": "fromInput", "contextWindowLength": int(window) if window else 10}


# --------------------------------------------------------------------------
# Triggers and data
# --------------------------------------------------------------------------


def for_form(node: Node, spec: Optional[WorkflowSpec] = None) -> Dict[str, Any]:
    """Form fields come from the sample payload, so the intake form on the
    canvas asks for exactly the fields the workflow goes on to use."""
    values = []
    sample = spec.input_sample if spec else None
    if isinstance(sample, dict):
        for key, value in list(sample.items())[:6]:
            if isinstance(value, (dict, list)):
                continue
            values.append({
                "fieldLabel": key.replace("_", " ").title(),
                "requiredField": True,
                "fieldType": "number" if isinstance(value, (int, float))
                             and not isinstance(value, bool) else "text",
            })
    return {"formTitle": node.label, "formFields": {"values": values}, "options": {}}


_PATH_SKIP = _LABEL_SKIP | {"new", "comes", "come", "incoming", "webhook", "trigger", "receive",
                            "received", "gets", "get"}


def _path_slug(label: str) -> str:
    words = [w for w in re.findall(r"[a-z0-9]+", strip_step(label).lower())
             if w not in _PATH_SKIP]
    return "-".join(words[:5]) or "incoming"


WEBHOOK_KEY = "trigger.webhook::"
ERROR_TRIGGER_KEY = "trigger.app:n8n:error_trigger"


def trigger_stand_in(node: Node, catalog: Any = None) -> Optional[str]:
    """The catalog key an app trigger compiles to when n8n's catalog has no
    entry for its app, else None (it keeps what the catalog resolved).

    The kind-level `trigger.app::` entry is whichever app trigger the harvest
    happened to see (Calendly), so it is right only for that app. Any other
    app trigger becomes n8n's Error Trigger when spec.declares_error_handler
    says it is an error handler, else a plain Webhook its app posts to; never
    another app's trigger. A business event with "error" in its op
    (sentry/new_error, stripe/payment_error) is a Webhook, not an Error
    Trigger, and the label is never enough. spec.is_error_trigger reads the
    result through n8n_entry, so the two always agree.
    """
    if node.kind != "trigger.app":
        return None
    if catalog is None:
        from .catalog import get_catalog
        catalog = get_catalog("n8n")
    if node.app:
        for key in ("{}:{}:{}".format(node.kind, node.app, node.op or ""),
                    "{}:{}:".format(node.kind, node.app)):
            if catalog.entries.get(key):
                return None
    generic = str((catalog.entries.get("trigger.app::") or {}).get("type", ""))
    generic_app = re.sub(r"(?i)trigger$", "", generic.rsplit(".", 1)[-1]).lower()
    if node.app and re.sub(r"[^a-z0-9]", "", node.app.lower()) == generic_app:
        return None
    if declares_error_handler(node) and catalog.entries.get(ERROR_TRIGGER_KEY):
        return ERROR_TRIGGER_KEY
    return WEBHOOK_KEY


def n8n_entry(node: Node, catalog: Any = None) -> Dict[str, Any]:
    """The catalog entry compile_n8n emits for `node`, found the compiler's
    way (exact -> kind:app: -> kind:: -> fallback, then trigger_stand_in for
    an app trigger) but read directly, so the catalog's usage report is left
    untouched. spec.is_error_trigger is this entry being the Error Trigger."""
    if catalog is None:
        from .catalog import get_catalog
        catalog = get_catalog("n8n")
    stand_in = trigger_stand_in(node, catalog)
    if stand_in and catalog.entries.get(stand_in):
        return catalog.entries[stand_in]
    for key in ("{}:{}:{}".format(node.kind, node.app or "", node.op or ""),
                "{}:{}:".format(node.kind, node.app or ""),
                "{}::".format(node.kind)):
        entry = catalog.entries.get(key)
        if entry:
            return entry
    fallbacks = catalog.fallbacks
    return (fallbacks.get(node.kind)
            or fallbacks.get(node.kind.split(".")[0])
            or fallbacks.get("app.action" if node.app else "default")
            or fallbacks["default"])


def is_webhook_trigger(node: Node) -> bool:
    """A webhook trigger, or an app trigger standing in as one."""
    return node.kind == "trigger.webhook" or trigger_stand_in(node) == WEBHOOK_KEY


def webhook_paths(spec: WorkflowSpec) -> Dict[str, str]:
    """A unique path per webhook trigger. Explicit paths are kept as written;
    generated ones never collide with them or with each other."""
    taken: Set[str] = set()
    out: Dict[str, str] = {}
    hooks = [n for n in spec.nodes if is_webhook_trigger(n)]
    for node in hooks:
        path = (node.params or {}).get("path")
        if isinstance(path, str) and path.strip():
            out[node.key] = path.strip()
            taken.add(path.strip())
    for node in hooks:
        if node.key in out:
            continue
        base = _path_slug(node.label)
        path, n = base, 2
        while path in taken:
            path = "{}-{}".format(base, n)
            n += 1
        taken.add(path)
        out[node.key] = path
    return out


def for_webhook(node: Node, spec: WorkflowSpec) -> Dict[str, Any]:
    return {"path": webhook_paths(spec).get(node.key, _path_slug(node.label))}


def for_filter(node: Node, spec: Optional[WorkflowSpec] = None,
               short: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """A Filter node keeps the same condition shape an If node uses."""
    return for_branch(node, spec, short)


def for_split(node: Node) -> Dict[str, Any]:
    """Batch size is the whole point of a loop node; an empty one says nothing."""
    size = _numeric_hint(node.label)
    return {"batchSize": int(size) if size else 10, "options": {}}


def for_aggregate(node: Node, sample: Dict[str, Any]) -> Dict[str, Any]:
    keys = list(sample)[:3] if isinstance(sample, dict) else []
    if not keys:
        return {"aggregate": "aggregateAllItemData", "options": {}}
    return {
        "fieldsToAggregate": {
            "fieldToAggregate": [{"fieldToAggregate": k} for k in keys]
        },
        "options": {},
    }


def for_wait(node: Node) -> Dict[str, Any]:
    # Labels carry a step prefix ("5 · Wait 1 Hour"); strip it before reading
    # the amount, otherwise the step number becomes the wait duration.
    bare = re.sub(r"^\s*\d+[a-z]?\s*[·.:-]\s*", "", node.label)
    amount = _numeric_hint(bare) or 1
    label = node.label.lower()
    unit = "days" if "day" in label else "hours" if "hour" in label else \
           "minutes" if "min" in label else "seconds" if "sec" in label else "days"
    return {"amount": int(amount), "unit": unit}


def for_merge(node: Node) -> Dict[str, Any]:
    return {"mode": "combine", "combineBy": "combineByPosition", "options": {}}


def _assignment(node: Node, key: str, value: str, kind: str) -> Dict[str, Any]:
    return {"id": _cid(node.key, key), "name": key, "value": value, "type": kind}


def for_set(node: Node, sample: Dict[str, Any], limit: int = 8) -> Dict[str, Any]:
    """A Set node listing the fields actually moving through it."""
    if not isinstance(sample, dict) or not sample:
        return {"options": {}}
    assignments = []
    for key, value in list(sample.items())[:limit]:
        assignments.append(_assignment(node, key, "={{ $json.%s }}" % key, _guess_type(value)))
    return {"assignments": {"assignments": assignments}, "options": {}}


_CLEAN_WORDS = ("standard", "normal", "clean", "tidy", "trim", "format", "lower")


def _set_value(key: str, label: str, spec: WorkflowSpec, in_input: bool,
               mentioned: List[str]) -> str:
    """A value expression for one Set field, shaped by what the label says
    the step does to it."""
    k = key.lower()
    source = _as_dict(spec.input_sample)
    name_src = "name" if "name" in source else ("full_name" if "full_name" in source else None)
    cleaning = any(w in label for w in _CLEAN_WORDS)
    if in_input:
        ref = "$json.%s" % key
        if "email" in k and cleaning:
            return "={{ (%s || '').trim().toLowerCase() }}" % ref
        if "phone" in k and ("e.164" in label or "e164" in label or cleaning):
            return "={{ '+' + String(%s || '').replace(/\\D/g, '') }}" % ref
        if cleaning and isinstance(source.get(key), str):
            return "={{ (%s || '').trim() }}" % ref
        return "={{ %s }}" % ref
    if k == "first_name" and name_src:
        return "={{ ($json.%s || '').trim().split(' ')[0] }}" % name_src
    if k == "last_name" and name_src:
        return "={{ ($json.%s || '').trim().split(' ').slice(1).join(' ') }}" % name_src
    if ("hash" in label or "idempot" in label or "dedupe" in label) and \
            (k.endswith("key") or k.endswith("hash") or k.endswith("id")):
        parts = [m for m in mentioned if m in source]
        if "timestamp" in label or "time" in label:
            parts += [s for s in source if s.endswith("_at") and s not in parts][:1]
        parts = parts or _scalar_keys(source)[:2]
        joined = "[{}].join('|')".format(", ".join("$json." + p for p in parts))
        if "hash" in label:
            joined += ".hash('sha256')"
        return "={{ %s }}" % joined
    if k.endswith("_at") or k in ("timestamp", "processed_at"):
        return "={{ $now.toISO() }}"
    return "={{ $json.%s }}" % key


def for_transform(node: Node, spec: WorkflowSpec) -> Dict[str, Any]:
    """A Set node whose fields come from what its label says it does.

    The first Set on a path lists the incoming payload; later ones list the
    fields their label names, or the shape of the step before them, so two
    Set nodes never show the same copy of the input.
    """
    label = strip_step(node.label).lower()
    words = _bare_words(node.label)
    source = _as_dict(spec.input_sample)
    first = not any(a.kind == "data.transform" for a in _ancestors(spec, node.key))

    fields: List[Tuple[str, Any, bool]] = []  # (key, sample value, in input)
    seen: Set[str] = set()

    def add(key: str, value: Any, in_input: bool) -> None:
        if key not in seen and len(fields) < 8:
            seen.add(key)
            fields.append((key, value, in_input))

    mentioned = [k for k in source if any(_key_matches(w, k) for w in words)]
    for key in mentioned:
        add(key, source[key], True)
    for key in _leaf_keys(spec.output_sample, depth=2):
        if key in source or not any(_key_matches(w, key) for w in words):
            continue
        add(key, _find_value(spec.output_sample, key), False)

    subset = bool(fields)
    if not fields:
        pred = _first_predecessor(spec, node.key)
        ai_keys = _ai_output_keys(pred, spec)
        if ai_keys:
            assignments = [_assignment(node, k, "={{ $json.output.%s }}" % k, _guess_type(v))
                           for k, v in list(ai_keys.items())[:8]]
            return {"assignments": {"assignments": assignments},
                    "includeOtherFields": True, "options": {}}
        if first or not spec.output_sample:
            params = for_set(node, spec.input_sample)
            params["includeOtherFields"] = False
            return params
        out = _as_dict(spec.output_sample)
        for key in _scalar_keys(out):
            add(key, out[key], key in source)
        subset = True
    assignments = [_assignment(node, key, _set_value(key, label, spec, in_input, mentioned),
                               _guess_type(value) if not isinstance(value, (dict, list))
                               else "string")
                   for key, value, in_input in fields]
    return {"assignments": {"assignments": assignments},
            "includeOtherFields": bool(subset), "options": {}}


def distinct_set_params(node: Node, spec: WorkflowSpec,
                        taken: Set[Tuple[str, ...]]) -> Dict[str, Any]:
    """Fields for a Set node whose synthesised list matched an earlier Set
    node's. It records which step ran and when, named from its own label
    ("Fix the Failing Record" -> `fix_failing_record_at`), and passes the
    item through, so no two Set nodes on a canvas show the same list."""
    label = strip_step(node.label)
    words = [w for w in _bare_words(node.label)
             if w not in GENERIC_VERBS and not w.isdigit() and len(w) > 2]
    base = "_".join(words[:3]) or "step"
    step = re.match(r"^\s*(\d+[a-z]?)", node.label or "")
    candidates = [base + "_at"]
    if step:
        candidates.append("{}_{}_at".format(base, step.group(1)))
    candidates.append("{}_{}_at".format(base, _cid(node.key)[:4]))
    stamp = candidates[-1]
    for name in candidates:
        if ("step", name) not in taken:
            stamp = name
            break
    assignments = [
        {"id": _cid(node.key, "step"), "name": "step", "value": label, "type": "string"},
        {"id": _cid(node.key, stamp), "name": stamp, "value": "={{ $now.toISO() }}",
         "type": "string"},
    ]
    return {"assignments": {"assignments": assignments}, "includeOtherFields": True,
            "options": {}}


def _find_value(sample: Any, key: str) -> Any:
    if isinstance(sample, dict):
        if key in sample:
            return sample[key]
        for value in sample.values():
            found = _find_value(value, key)
            if found is not None:
                return found
    return None


def for_code(node: Node, sample: Dict[str, Any]) -> Dict[str, Any]:
    keys = list(sample)[:4] if isinstance(sample, dict) else []
    picks = "\n".join("    {}: item.json.{},".format(k, k) for k in keys)
    return {
        "jsCode": (
            "// {}\n"
            "return items.map(item => ({{\n"
            "  json: {{\n"
            "{}\n"
            "    processed_at: new Date().toISOString(),\n"
            "  }},\n"
            "}}));".format(node.label, picks)
        )
    }


def config_node_params(config: Dict[str, Any]) -> Dict[str, Any]:
    """The "0 - Config: Your Settings" Set node: one field per setting, and
    everything from the trigger passes through untouched."""
    assignments = []
    for key, value in config.items():
        kind = _guess_type(value)
        if kind in ("array", "object"):
            value, kind = json.dumps(value), "string"
        assignments.append({"id": _cid(CONFIG_NODE_KEY, key), "name": key,
                            "value": value, "type": kind})
    return {"mode": "manual", "assignments": {"assignments": assignments},
            "includeOtherFields": True, "options": {}}


# --------------------------------------------------------------------------
# HTTP services
# --------------------------------------------------------------------------

_SERVICES_CACHE: Dict[str, Any] = {}


def load_services() -> Dict[str, Any]:
    if "services" not in _SERVICES_CACHE:
        with open(_SERVICES_PATH, "r", encoding="utf-8") as fh:
            _SERVICES_CACHE["services"] = json.load(fh).get("services", {})
    return _SERVICES_CACHE["services"]


def _alias_hit(alias: str, text: str) -> bool:
    return re.search(r"(?<![a-z0-9])" + re.escape(alias.lower()) + r"(?![a-z0-9])",
                     text) is not None


def match_service(node: Node, explicit: Optional[str] = None) -> Optional[str]:
    """Which service a node calls: the `service` shorthand, the node's app, or
    the service named in its label."""
    services = load_services()
    names = [explicit, node.app]
    for name in names:
        if not name:
            continue
        low = str(name).lower().replace("_", "").replace(" ", "")
        for key, svc in services.items():
            options = [key] + list(svc.get("aliases", [])) + list(svc.get("strict_aliases", []))
            if low in [o.lower().replace(" ", "").replace("_", "") for o in options]:
                return key
    bare = strip_step(node.label).lower()
    first_word = (re.findall(r"[a-z0-9.]+", bare) or [""])[0]
    for key, svc in services.items():
        for alias in svc.get("aliases", []):
            if _alias_hit(alias, bare):
                return key
        for alias in svc.get("strict_aliases", []):
            a = alias.lower()
            if first_word == a or re.search(r"(?<![a-z0-9])" + re.escape(a) + r"\s*:", bare):
                return key
    return None


def _pick_operation(service: Dict[str, Any], label: str,
                    explicit: Optional[str] = None) -> Tuple[str, Dict[str, Any]]:
    ops = service.get("operations", {})
    if explicit and explicit in ops:
        return explicit, ops[explicit]
    text = strip_step(label).lower()
    best_key, best_score = None, 0
    for key, op in ops.items():
        score = sum(weight for word, weight in op.get("keywords", {}).items() if word in text)
        if score > best_score:
            best_key, best_score = key, score
    if best_key is None:
        best_key = service.get("default_op") or next(iter(ops))
    return best_key, ops[best_key]


HTTP_NODE_TYPE = "n8n-nodes-base.httpRequest"


def compiles_to_http(node: Node) -> bool:
    """Whether the n8n catalog turns this node into an HTTP Request node.

    A net.http node always does. An app.action does only when the catalog has
    no native node for its app and it falls back to HTTP; a native node
    (monday -> mondayCom) never does. Calendly has no native action node, so
    a Calendly action is an HTTP Request against its API. The catalog's
    entries are read directly so the check leaves its usage report untouched.
    """
    if node.kind == "net.http":
        return True
    if node.kind != "app.action":
        return False
    from .catalog import get_catalog
    catalog = get_catalog("n8n")
    for key in ("{}:{}:{}".format(node.kind, node.app or "", node.op or ""),
                "{}:{}:".format(node.kind, node.app or ""),
                "{}::".format(node.kind)):
        entry = catalog.entries.get(key)
        if entry:
            return entry.get("type") == HTTP_NODE_TYPE
    entry = (catalog.fallbacks.get(node.kind) or catalog.fallbacks.get("app")
             or catalog.fallbacks.get("app.action" if node.app else "default")
             or catalog.fallbacks.get("default") or {})
    return entry.get("type") == HTTP_NODE_TYPE


def resolve_service(node: Node, spec: Optional[WorkflowSpec] = None
                    ) -> Optional[Tuple[str, Dict[str, Any], str, Dict[str, Any]]]:
    """(service key, service, operation key, operation) or None. Only nodes
    that compile to an n8n HTTP Request node resolve; a native app node keeps
    its own credential and never adds Config keys or "add your API token"
    setup lines."""
    if node.kind not in ("net.http", "app.action") or not compiles_to_http(node):
        return None
    params = node.params or {}
    explicit = params.get("service")
    explicit = explicit if isinstance(explicit, str) else None
    if node.kind == "app.action" and not explicit:
        # A native app node (Sheets, Slack) is never re-read as an API call
        # because its label mentions a service; only its own app counts.
        key = match_service(Node(key=node.key, kind=node.kind, label="", app=node.app))
    else:
        key = match_service(node, explicit)
    if not key:
        return None
    service = load_services()[key]
    wanted = params.get("operation") if isinstance(params.get("operation"), str) else node.op
    op_key, op = _pick_operation(service, node.label, wanted)
    return key, service, op_key, op


_TOKEN = re.compile(r"\{(config|field|json|js):([^{}]+)\}")


class _Render(object):
    """Turns service templates into n8n values for one node."""

    def __init__(self, spec: Optional[WorkflowSpec], service: Dict[str, Any],
                 node: Optional[Node] = None) -> None:
        self.spec = spec
        self.service = service
        self.node = node

    def placeholder(self, key: str) -> str:
        return str(self.service.get("placeholders", {}).get(key, placeholder_value(key)))

    def token(self, kind: str, arg: str, quoted: bool) -> str:
        if kind == "config":
            expr = config_expr(self.node, self.spec, arg)
            if expr:
                return "{{ %s }}" % expr
            return self.placeholder(arg)
        if kind == "field":
            return "{{ %s }}" % field_ref(self.node, self.spec, arg)
        if kind == "json":
            return "{{ JSON.stringify(%s) }}" % field_ref(self.node, self.spec, arg)
        return "{{ %s }}" % arg  # js

    def text(self, template: str) -> str:
        """A plain string value (URL, header, query). '=' prefixed when it
        contains an expression."""
        out = _TOKEN.sub(lambda m: self.token(m.group(1), m.group(2), False), template)
        return ("=" + out) if "{{" in out else out

    def body(self, template: Any) -> str:
        """A JSON body as n8n's jsonBody expression string."""
        if template == "__sample_row__":
            row = {k: "{field:%s}" % k for k in _scalar_keys(self.spec.input_sample if
                                                             self.spec else {})[:8]}
            template = row or {"data": "{js:JSON.stringify($json)}"}
        raw_marks: Dict[str, str] = {}

        def convert(value: Any) -> Any:
            if isinstance(value, dict):
                return {k: convert(v) for k, v in value.items()}
            if isinstance(value, list):
                return [convert(v) for v in value]
            if isinstance(value, str):
                whole = _TOKEN.fullmatch(value)
                if whole and whole.group(1) in ("json", "js"):
                    mark = "__RAW_%d__" % len(raw_marks)
                    raw_marks[mark] = self.token(whole.group(1), whole.group(2), False)
                    return mark
                return _TOKEN.sub(lambda m: self.token(m.group(1), m.group(2), True), value)
            return value

        text = _dumps(convert(template))
        for mark, expr in raw_marks.items():
            text = text.replace('"%s"' % mark, expr)
        return "=" + text


def service_config_keys(spec: WorkflowSpec, nodes: Optional[List[Node]] = None
                        ) -> Dict[str, str]:
    """Every Config setting these HTTP nodes (default: all of the spec's)
    read, with its placeholder, so the Config node can carry them."""
    out: Dict[str, str] = {}
    for node in (spec.nodes if nodes is None else nodes):
        found = resolve_service(node, spec)
        if not found:
            continue
        _, service, _, op = found
        blob = json.dumps([service.get("base_url"), service.get("auth"),
                           service.get("headers"), op])
        for key in re.findall(r"\{config:([^{}]+)\}", blob):
            out.setdefault(key, str(service.get("placeholders", {}).get(
                key, placeholder_value(key))))
    return out


def node_reads_config(node: Node, spec: WorkflowSpec) -> bool:
    """Whether this node would read a Config setting if one were upstream:
    an HTTP service template with a {config:...} token, or a Sheets/Airtable
    node whose document comes from a config key."""
    found = resolve_service(node, spec)
    if found:
        _, service, _, op = found
        blob = json.dumps([service.get("base_url"), service.get("auth"),
                           service.get("headers"), op])
        if "{config:" in blob:
            return True
    if node.kind == "app.action" and node.app in _TABLE_NEEDLES and \
            not (node.params or {}).get("document"):
        return _config_key(spec, _TABLE_NEEDLES[node.app]) is not None
    return False


def _kv_list(pairs: Dict[str, str]) -> Dict[str, Any]:
    return {"parameters": [{"name": k, "value": v} for k, v in pairs.items()]}


def for_http(node: Node, existing: Dict[str, Any], spec: Optional[WorkflowSpec] = None,
             short: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """An HTTP Request against a real endpoint where the service is known.

    Resolution: the `service` shorthand, the node's app, or the service named
    in the label ("GHL: Upsert Contact"). Auth values are never real keys:
    they read from the Config node upstream of this node when there is one,
    else they are a literal placeholder such as `Bearer PASTE-YOUR-GHL-API-KEY`.
    An unmatched node
    keeps an obviously fake example.com URL so nobody mistakes it for real.
    """
    short = short or {}
    params = dict(existing)
    if "example.com/resource" in str(params.get("url", "")):
        params["url"] = ""

    found = resolve_service(node, spec)
    if found:
        _, service, _, op = found
        render = _Render(spec, service, node)
        method = str(short.get("method") or op.get("method") or "POST").upper()
        params["method"] = method
        params["url"] = render.text(service.get("base_url", "") + op.get("path", ""))

        headers: Dict[str, str] = {}
        query: Dict[str, str] = {}
        auth = service.get("auth")
        if isinstance(auth, dict):
            target = headers if auth.get("in") == "header" else query
            target[auth["name"]] = render.text(auth["value"])
        for name, value in dict(service.get("headers") or {}).items():
            headers[name] = render.text(value)
        for name, value in dict(op.get("headers") or {}).items():
            headers[name] = render.text(value)
        for name, value in dict(op.get("query") or {}).items():
            query[name] = render.text(value)
        if headers:
            params["sendHeaders"] = True
            params["headerParameters"] = _kv_list(headers)
        if query:
            params["sendQuery"] = True
            params["queryParameters"] = _kv_list(query)
        if op.get("body") is not None and method not in ("GET",):
            params["sendBody"] = True
            params["specifyBody"] = "json"
            params["jsonBody"] = render.body(op["body"])
        else:
            for key in ("sendBody", "specifyBody", "jsonBody"):
                params.pop(key, None)

    if short.get("method"):
        params["method"] = str(short["method"]).upper()
    if short.get("url"):
        url = str(short["url"])
        params["url"] = ("=" + url) if "{{" in url and not url.startswith("=") else url
    if isinstance(short.get("headers"), dict):
        merged: Dict[str, str] = {}
        for item in (params.get("headerParameters") or {}).get("parameters", []):
            merged[item["name"]] = item["value"]
        for name, value in short["headers"].items():
            value = str(value)
            merged[str(name)] = ("=" + value) if "{{" in value and not value.startswith("=") \
                else value
        params["sendHeaders"] = True
        params["headerParameters"] = _kv_list(merged)
    if "body" in short and short["body"] is not None:
        body = short["body"]
        params["sendBody"] = True
        params["specifyBody"] = "json"
        if isinstance(body, (dict, list)):
            params["jsonBody"] = "=" + _dumps(body)
        else:
            params["jsonBody"] = _as_expression(body)

    if not params.get("url"):
        slug = re.sub(r"[^a-z0-9]+", "-", (node.app or strip_step(node.label)).lower()).strip("-")
        params["url"] = "https://api.{}.example.com/v1/{}".format(
            re.sub(r"[^a-z0-9]+", "", (node.app or "service").lower()) or "service",
            slug[:40] or "resource"
        )
    params.setdefault("method", "POST")
    if str(params.get("method")).upper() == "GET":
        for key in ("sendBody", "specifyBody", "jsonBody"):
            params.pop(key, None)
    # Retry and timeout are what a reviewer looks for to tell whether the person
    # has actually run something in production. Retries are node settings, not
    # parameters; the compiler lifts them to the node.
    options = dict(params.get("options") or {})
    options.setdefault("timeout", 15000)
    params["options"] = options
    params.setdefault("retryOnFail", True)
    params.setdefault("maxTries", 3)
    return params


# --------------------------------------------------------------------------
# Apps
# --------------------------------------------------------------------------

# Plausible field values per app. A node showing real fields sells the
# workflow; the same node showing nothing undoes the label above it. Unknown
# keys are ignored by n8n, so a wrong guess costs nothing while a right one
# costs no more. Slack, Sheets and Airtable are built by their own functions.
_APP_FIELDS = {
    "twilio":         {"to": "={{ $json.callback_number || $json.phone }}", "message": "={{ $json.message }}"},
    "gmail":          {"sendTo": "={{ $json.email }}", "subject": "={{ $json.subject }}", "message": "={{ $json.body }}", "options": {}},
    "outlook":        {"toRecipients": "={{ $json.email }}", "subject": "={{ $json.subject }}"},
    "notion":         {"propertiesUi": {"propertyValues": []}, "options": {}},
    "hubspot":        {"email": "={{ $json.email }}", "additionalFields": {}},
    "salesforce":     {"email": "={{ $json.email }}", "additionalFields": {}},
    "googleCalendar": {"start": "={{ $json.starts_at }}", "end": "={{ $json.ends_at }}", "additionalFields": {"summary": "={{ $json.title }}"}},
    "telegram":       {"text": "={{ $json.message }}", "additionalFields": {}},
    "whatsapp":       {"textBody": "={{ $json.message }}"},
    "discord":        {"content": "={{ $json.message }}", "options": {}},
    "googleDocs":     {"folderId": "root", "title": "={{ $json.title }}"},
    "googleDrive":    {"name": "={{ $json.filename }}", "options": {}},
    "html":           {"operation": "extractHtmlContent", "extractionValues": {"values": [{"key": "content", "cssSelector": "main", "returnValue": "text"}]}, "options": {}},
    "extractFile":    {"operation": "pdf", "options": {"joinPages": True}},
    "stripe":         {"resource": "customer", "operation": "get", "customerId": "={{ $json.customer_id }}"},
    "shopify":        {"resource": "order", "operation": "get", "orderId": "={{ $json.order_id }}"},
    "quickbooks":     {"resource": "bill", "operation": "create", "additionalFields": {}},
    "wordpress":      {"title": "={{ $json.title }}", "additionalFields": {"content": "={{ $json.body }}", "status": "draft"}},
    "openai":         {"modelId": {"__rl": True, "mode": "list", "value": "gpt-4.1"}, "options": {}},
    "postgres":       {"query": "SELECT * FROM records WHERE id = $1;", "options": {}},
}

_PRIORITY_FIELDS = ("name", "full_name", "first_name", "company", "company_name", "email",
                    "phone", "summary", "status", "score")


def _message_fields(node: Node, spec: WorkflowSpec, count: int = 3) -> List[str]:
    """Real fields for a notification: the ones the label names first."""
    words = _bare_words(node.label)
    keys = _all_keys(spec)
    source = _scalar_keys(spec.input_sample)
    chosen: List[str] = []
    for key in keys:
        if any(_key_matches(w, key) for w in words) and key not in chosen:
            if not isinstance(_find_value(spec.output_sample, key), (dict, list)) or \
                    key in source:
                chosen.append(key)
    for key in _PRIORITY_FIELDS:
        if key in source and key not in chosen:
            chosen.append(key)
    for key in source:
        if key not in chosen:
            chosen.append(key)
    return chosen[:count]


def _slack_channel(node: Node, spec: WorkflowSpec) -> str:
    label = strip_step(node.label).lower()
    section_label = ""
    for section in spec.sections:
        if section.key == node.section:
            section_label = section.label.lower()
    both = label + " " + section_label
    if re.search(r"\b(alert|alerts|fail|fails|failed|failure|error|errors)\b", label) or \
            _on_error_path(node, spec):
        return "#ops-alerts"
    if re.search(r"\b(review|approv\w*|queue|manual)\b", label):
        return "#review-queue"
    if re.search(r"\b(sales|deal|deals|quote|won|closed)\b", both):
        return "#sales"
    if re.search(r"\b(support|ticket|tickets|escalat\w*)\b", both):
        return "#support"
    if re.search(r"\b(lead|leads|enquir\w*|inquir\w*|prospect\w*)\b", both):
        return "#new-leads"
    words = [w for w in _bare_words(section_label or label)
             if not w.isdigit() and w not in ("never", "every", "one", "into")]
    return "#" + ("-".join(words[:2]) or "automation")


def slack_text(node: Node, spec: WorkflowSpec) -> str:
    if _on_error_path(node, spec):
        return ("=:rotating_light: *{}* failed at *{{{{ $json.execution.lastNodeExecuted }}}}*\n"
                "{{{{ $json.execution.error.message }}}}\n"
                "Open the failed run: {{{{ $json.execution.url }}}}".format(spec.title.strip()))
    lines = ["*{}*".format(strip_step(node.label).rstrip(" .?"))]
    for key in _message_fields(node, spec):
        lines.append("{}: {{{{ {} }}}}".format(_pretty(key), field_ref(node, spec, key)))
    return "=" + "\n".join(lines)


def for_slack(node: Node, spec: WorkflowSpec, short: Dict[str, Any],
              existing: Dict[str, Any]) -> Dict[str, Any]:
    params: Dict[str, Any] = {"select": "channel",
                              "otherOptions": {"includeLinkToWorkflow": False}}
    channel = short.get("channel") or _slack_channel(node, spec)
    params["channelId"] = {"__rl": True, "mode": "name", "value": str(channel)}
    text = short.get("text")
    params["text"] = _as_expression(text) if text and "{{" in str(text) else \
        (str(text) if text else slack_text(node, spec))
    return params


def _snake(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(name).lower()).strip("_") or "field"


_SHEET_SKIP = {"append", "add", "write", "update", "upsert", "save", "insert", "push", "row",
               "rows", "sheet", "sheets", "google", "record", "records", "new", "table",
               "airtable", "base", "tab"}

# Verbs that lead a Sheets/Airtable step label. A tab is named for what it
# holds, so "Mark the Row Handled" never becomes a tab called "Mark Handled".
# Leading verbs are dropped; later in the label only the generic verbs and
# status words are, so "Execution Log Row" keeps its noun "Log".
_SHEET_VERBS = GENERIC_VERBS | {
    "log", "logs", "mark", "marks", "park", "parks", "write", "writes", "read", "reads",
    "look", "lookup", "find", "fetch", "pull", "load", "move", "sync", "store", "track",
    "record", "flag", "tag", "delete", "remove", "clear", "append", "upsert", "insert",
    "save", "push", "copy", "list", "search", "match",
}
_SHEET_NOISE = GENERIC_VERBS | {"handled", "done", "processed", "it", "them", "each", "one",
                                "every", "into", "out", "back", "up"}


def _sheet_name(node: Node) -> str:
    words = [w for w in _bare_words(node.label) if w not in _SHEET_SKIP and not w.isdigit()]
    while words and words[0] in _SHEET_VERBS:
        words = words[1:]
    words = [w for w in words if w not in _SHEET_NOISE]
    return " ".join(w.capitalize() for w in words[:2]) or "Sheet1"


def _default_columns(node: Node, spec: WorkflowSpec) -> List[str]:
    words = _bare_words(node.label)
    nested, score = _best_sample_dict(words, spec.output_sample)
    if nested and score >= 2:
        cols = _scalar_keys(nested) + [k for k, v in nested.items() if isinstance(v, list)]
        return cols[:12]
    cols: List[str] = []
    for sample in (spec.output_sample, spec.input_sample):
        for key in _scalar_keys(sample):
            if key not in cols:
                cols.append(key)
    return cols[:10]


def _mapping(columns: List[str], operation: str) -> Dict[str, Any]:
    value = {}
    schema = []
    for col in columns:
        value[col] = "={{ $json.%s }}" % _snake(col)
    match = None
    for col in columns:
        low = _snake(col)
        if low == "id" or low.endswith("_id") or low.endswith("_key") or low == "email":
            match = col
            break
    match = match or (columns[0] if columns else None)
    for col in columns:
        schema.append({"id": col, "displayName": col, "required": False,
                       "defaultMatch": col == match, "display": True, "type": "string",
                       "canBeUsedToMatch": True})
    out: Dict[str, Any] = {"mappingMode": "defineBelow", "value": value,
                           "matchingColumns": [match] if match and operation in (
                               "appendOrUpdate", "update", "upsert") else [],
                           "schema": schema}
    return out


def _rl(value: str, default_mode: str = "id") -> Dict[str, Any]:
    text = str(value)
    if text.startswith("http"):
        return {"__rl": True, "mode": "url", "value": text}
    if "{{" in text:
        return {"__rl": True, "mode": "id", "value": _as_expression(text)}
    return {"__rl": True, "mode": default_mode, "value": text}


_TABLE_NEEDLES = {"googleSheets": ("sheet", "spreadsheet"), "airtable": ("airtable", "base")}
_TABLE_PLACEHOLDER = {"googleSheets": "google_sheet_id", "airtable": "airtable_base_id"}
# Operations that act on rows an earlier step wrote.
_REUSE_OPS = {"update", "read", "get", "getall", "search", "lookup", "list", "delete"}


def _config_key(spec: WorkflowSpec, needles: Tuple[str, ...]) -> Optional[str]:
    for key in spec.config:
        if any(n in key.lower() for n in needles):
            return key
    return None


def _config_lookup(node: Node, spec: WorkflowSpec, needles: Tuple[str, ...]) -> Optional[str]:
    """A Config reference for the first config key a needle names, only when
    a Config node is upstream of this node."""
    key = _config_key(spec, needles)
    if key is None:
        return None
    expr = config_expr(node, spec, key)
    return "={{ %s }}" % expr if expr else None


def _table_operation(node: Node, existing: Dict[str, Any]) -> str:
    raw = (node.params or {}).get("operation")
    return str(raw or existing.get("operation") or node.op or "")


def _upstream_table(node: Node, spec: WorkflowSpec) -> Optional[Node]:
    """The nearest upstream node on the same table app (Sheets or Airtable)."""
    for ancestor in _ancestors(spec, node.key):
        if ancestor.kind == "app.action" and ancestor.app == node.app:
            return ancestor
    return None


def _table_target(node: Node, spec: WorkflowSpec, short: Dict[str, Any],
                  existing: Dict[str, Any], depth: int = 0) -> Tuple[str, str]:
    """(document, sheet or table) for a Sheets/Airtable node.

    Explicit shorthand wins. An update or read step works on the rows an
    earlier step wrote, so it reuses the nearest upstream node's document and
    tab. Otherwise the document reads from the Config node upstream, else a
    PASTE-YOUR- placeholder, and the tab is named from the label's nouns.
    """
    app = node.app or ""
    document = short.get("document")
    sheet = short.get("sheet")
    operation = _table_operation(node, existing).lower()
    op = (node.op or "").lower()
    if (not document or not sheet) and depth < 6 and \
            (operation in _REUSE_OPS or op in _REUSE_OPS):
        upstream = _upstream_table(node, spec)
        if upstream is not None:
            up_short, _ = split_shorthand(upstream)
            up_doc, up_sheet = _table_target(upstream, spec, up_short, {}, depth + 1)
            document = document or up_doc
            sheet = sheet or up_sheet
    if not document:
        document = _config_lookup(node, spec, _TABLE_NEEDLES.get(app, ("sheet",))) or \
            placeholder_value(_TABLE_PLACEHOLDER.get(app, "document_id"))
    if not sheet:
        sheet = _sheet_name(node)
    return str(document), str(sheet)


def for_table(node: Node, spec: WorkflowSpec, short: Dict[str, Any],
              existing: Dict[str, Any]) -> Dict[str, Any]:
    """Google Sheets / Airtable with a named document, sheet and real columns."""
    app = node.app
    params: Dict[str, Any] = {}
    columns = short.get("columns") if isinstance(short.get("columns"), list) else None
    operation = str(existing.get("operation") or "")
    reading = operation in ("read", "search", "get", "getAll", "list", "lookup")
    document, sheet = _table_target(node, spec, short, existing)
    if app == "googleSheets":
        params["documentId"] = _rl(document, "id")
        params["sheetName"] = {"__rl": True, "mode": "name", "value": sheet}
    else:
        params["base"] = _rl(document, "id")
        params["table"] = {"__rl": True, "mode": "id", "value": sheet}
    if not reading:
        cols = [str(c) for c in (columns or _default_columns(node, spec))]
        if cols:
            params["columns"] = _mapping(cols, operation)
    params.setdefault("options", {})
    return params


def for_app_action(node: Node, existing: Dict[str, Any], spec: Optional[WorkflowSpec] = None,
                   short: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Fill an app node with fields that reference the data flowing into it."""
    short = short or {}
    params = dict(existing)
    if spec is not None and node.app == "slack":
        params.update(for_slack(node, spec, short, existing))
    elif spec is not None and node.app in ("googleSheets", "airtable"):
        params.update(for_table(node, spec, short, existing))
    for key, value in _APP_FIELDS.get(node.app or "", {}).items():
        params.setdefault(key, value)
    return params


# --------------------------------------------------------------------------
# Shorthand
# --------------------------------------------------------------------------

# Exact shorthand keys per node shape. A shorthand key is translated into real
# n8n parameters and never reaches the workflow JSON itself.
SHORTHAND_KEYS: Dict[str, Tuple[str, ...]] = {
    "flow.branch": ("condition",),
    "data.filter": ("condition",),
    "ai.llm": ("prompt", "system_message"),
    "ai.agent": ("prompt", "system_message"),
    "ai.parser": ("schema",),
    "net.http": ("service", "operation", "method", "url", "headers", "body"),
    "trigger.webhook": ("path",),
    "app:slack": ("channel", "text"),
    "app:googleSheets": ("document", "sheet", "columns"),
    "app:airtable": ("document", "sheet", "columns"),
}


def _shorthand_names(node: Node, http: bool) -> Tuple[str, ...]:
    if node.kind == "app.action":
        names = SHORTHAND_KEYS.get("app:" + (node.app or ""), ())
        return names + (SHORTHAND_KEYS["net.http"] if http else ())
    return SHORTHAND_KEYS.get(node.kind, ())


def split_shorthand(node: Node, http: bool = False) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """(shorthand, raw n8n params) for one node.

    `columns` is shorthand only as a list; a dict is n8n's own mapping object
    and passes through raw.
    """
    names = _shorthand_names(node, http)
    short: Dict[str, Any] = {}
    raw: Dict[str, Any] = {}
    for key, value in (node.params or {}).items():
        if key in names and not (key == "columns" and isinstance(value, dict)):
            short[key] = value
        else:
            raw[key] = value
    return short, raw


# Node-level settings that some synthesis puts in parameters. n8n reads them
# from the node itself, so the compiler lifts them out.
NODE_SETTINGS = ("retryOnFail", "maxTries", "waitBetweenTries", "alwaysOutputData",
                 "onError", "executeOnce")


def enrich(node: Node, spec: WorkflowSpec, base: Dict[str, Any]) -> Dict[str, Any]:
    """Catalog defaults, then synthesised config, then the spec's raw params.

    Shorthand in node.params is translated here and removed; everything else in
    node.params is a raw n8n parameter and wins over what was synthesised.
    """
    params = dict(base)
    http = node.kind == "net.http" or (node.kind == "app.action" and "url" in params)
    short, raw = split_shorthand(node, http)

    if node.kind == "flow.branch":
        params.update(for_branch(node, spec, short))
    elif node.kind == "flow.switch":
        edges = spec.successors(node.key, include_loops=True)
        if edges:
            params.update(for_switch(node, edges, spec))
    elif is_config_node(node):
        params.update(config_node_params(spec.config))
    elif node.kind == "data.transform":
        params.update(for_transform(node, spec))
    elif node.kind == "data.code":
        params.update(for_code(node, spec.input_sample))
    elif node.kind == "data.filter":
        params.update(for_filter(node, spec, short))
    elif node.kind == "data.split":
        params.update(for_split(node))
    elif node.kind == "data.aggregate":
        params.update(for_aggregate(node, spec.output_sample or spec.input_sample))
    elif node.kind == "data.merge":
        params.update(for_merge(node))
    elif node.kind == "flow.wait":
        params.update(for_wait(node))
    elif node.kind == "ai.llm":
        params.update(for_llm(node, spec, short))
    elif node.kind == "ai.agent":
        params.update(for_agent(node, spec, short, params))
    elif node.kind == "ai.parser":
        params.update(for_parser(node, spec, short, params))
    elif node.kind == "ai.memory":
        params.update(for_memory(node))
    elif node.kind == "trigger.form":
        params.update(for_form(node, spec))
    elif is_webhook_trigger(node):
        params.update(for_webhook(node, spec))
    elif http or params.get("url") is not None:
        params = for_http(node, params, spec, short)
    elif node.kind == "app.action":
        params = for_app_action(node, params, spec, short)

    params.update(raw)

    # A hand-written JSON Schema replaces the example; leaving the catalog's
    # default example beside it shows a second, wrong schema on the canvas.
    if node.kind == "ai.parser" and (raw.get("inputSchema") or (
            params.get("inputSchema") and params.get("schemaType") == "manual")):
        if "jsonSchemaExample" not in raw:
            params.pop("jsonSchemaExample", None)
        if "schemaType" not in raw:
            params["schemaType"] = "manual"

    # An LLM chain or agent with a parser sub-node must say so, or n8n draws
    # the parser disconnected from its parent.
    if node.kind in ("ai.llm", "ai.agent") and any(
            c.kind == "ai.parser" for c in spec.children_of(node.key)):
        params.setdefault("hasOutputParser", True)

    return params
