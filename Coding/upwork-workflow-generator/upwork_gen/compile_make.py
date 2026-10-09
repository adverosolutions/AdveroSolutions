"""WorkflowSpec -> Make.com blueprint JSON.

Make's model differs from n8n's in three ways that matter here:

* **Flow is nested, not a graph.** There is no edge list — branches live inside
  a `builtin:BasicRouter`'s `routes` array. The spec's DAG is walked into that
  shape, emitting each node exactly once; where two branches reconverge, the
  tail stays on the branch that reached it first rather than being duplicated.
* **There is no `pinData`.** Sample data is carried by two real modules instead:
  a "Sample Input" set-variable right after the trigger and a "Final Output"
  set-variable at the end. Both are clickable on camera and show their values,
  which reproduces the n8n pinned-data beat using ordinary Make primitives.
* **Scheduling is not a module.** A scheduled scenario carries its cadence in
  scenario settings, so `trigger.schedule` sets `instant: false` rather than
  emitting a trigger module of its own.

Mappers are filled from the spec's own data rather than a placeholder. A Make
webhook bundle exposes the payload's top-level keys by name, so every
downstream module maps `{{1.<key>}}` (or `{{1.parent.child}}`) for the sample
fields its label talks about. AI modules get a system prompt written from the
spec title, the section note and the step itself; Slack posts go to the
channel the spec names (`channel_name`, else #general); Sheets and Airtable
rows get real columns, each mapped only to a field of exactly its name, and
left blank otherwise. Section notes become Make canvas notes on the first
module of each section.

Explicit spec params win and are used as written. n8n expression syntax is
never shipped: it is left blank and reported (`compile_make_with_warnings`).
"""

from __future__ import annotations

import html
import json
import re
import unicodedata
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from .catalog import Catalog, get_catalog
from .spec import Node, WorkflowSpec

X_STEP = 300            # Make lays modules out on a fixed horizontal pitch
ROUTE_Y_STEP = 150      # vertical offset between a router's branches


# Make has no merge node, so where two branches converge the shared tail is
# repeated in each route — which is how real Make scenarios are built. The cap
# stops a diamond-heavy graph from expanding without bound.
MAX_COPIES = 4

# The trigger is always emitted first, so it is always module 1.
TRIGGER_ID = 1

# Canvas notes, in the shape real exports carry under `metadata.notes`
# (verified against public exports, e.g. github.com/shorin-nikita/PrideAIBot
# make/blueprint-connect-wazzup.json and github.com/Ekisa02/QXBoost-Automation
# "QXBOOST TEAM.blueprint.json"): moduleIds + HTML content + isFilterNote +
# metadata.color. #9138FE is the default purple both exports use.
NOTE_COLOR = "#9138FE"


# --------------------------------------------------------------------------
# Text helpers
# --------------------------------------------------------------------------

_ASCII_SWAPS = {"\u00b7": "-", "\u2014": "-", "\u2013": "-", "\u2019": "'",
                "\u2018": "'", "\u201c": '"', "\u201d": '"', "\u2192": "->",
                "\u2265": ">=", "\u2264": "<=", "\u00d7": "x", "\u2026": "...",
                "\u2713": "", "\u2022": "-"}


def _ascii(text: Any) -> str:
    """Everything this module writes is plain ASCII; spec text may not be."""
    out = str(text or "")
    for src, dst in _ASCII_SWAPS.items():
        out = out.replace(src, dst)
    out = unicodedata.normalize("NFKD", out)
    return re.sub(r"[ \t]{2,}", " ", out.encode("ascii", "ignore").decode("ascii")).strip()


_STEP_PREFIX = re.compile(r"^\s*\d+[a-z]?\s*[\u00b7.:\-\u2014\u2013]\s*", re.IGNORECASE)
_APP_PREFIX = re.compile(r"^([A-Za-z][\w /&.]{0,24}):\s+")


def _bare_label(label: str) -> str:
    """"3 - OpenAI: Write the SMS" -> "Write the SMS".

    The part before a colon is dropped only when it reads like an app name
    (short, no filler words), so "Suggest Reply to Rep: Approve or Edit"
    keeps its meaning."""
    text = _STEP_PREFIX.sub("", str(label or ""))
    match = _APP_PREFIX.match(text)
    if match:
        prefix_words = _raw_words(match.group(1))
        if len(prefix_words) <= 3 and not any(w in _STOP for w in prefix_words):
            text = text[match.end():]
    return _ascii(text).strip(" ?.") or _ascii(label)


_STOP = {
    "the", "a", "an", "and", "or", "of", "to", "for", "in", "on", "at", "by",
    "it", "is", "its", "into", "from", "with", "then", "that", "this", "each",
    "every", "any", "all", "who", "what", "if", "our", "your", "we", "you",
    "new", "one", "get", "set", "via", "per", "as", "be", "do", "does", "did",
    "was", "are", "step", "them", "their", "they", "me", "my", "so", "not",
}


def _raw_words(text: str) -> List[str]:
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(text))
    return [w for w in re.split(r"[^A-Za-z0-9]+", spaced.lower()) if w]


def _stem(word: str) -> str:
    if word.endswith("sses"):
        return word[:-2]
    for suffix in ("ing", "ed", "s"):
        if word.endswith(suffix) and not word.endswith("ss") and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)]
    return word


def _tokens(text: str) -> Set[str]:
    return {_stem(w) for w in _raw_words(text) if w not in _STOP and not w.isdigit()}


# --------------------------------------------------------------------------
# n8n syntax guard
# --------------------------------------------------------------------------

# A leading "=", `$json`, `$(...)` or `{{ $...` is n8n expression syntax. Make
# cannot evaluate it, so a value carrying it is never shipped.
_N8N_EXPR = re.compile(r"^\s*=|\$json\b|\$\(|\{\{\s*\$")
_N8N_OBJECT_KEYS = frozenset({"mappingMode", "__rl", "messageValues"})


def _n8n_syntax(value: Any) -> bool:
    """True when `value` (at any depth) holds n8n expression syntax or is an
    n8n-shaped object."""
    if isinstance(value, str):
        return bool(_N8N_EXPR.search(value))
    if isinstance(value, dict):
        return bool(_N8N_OBJECT_KEYS & set(value)) or any(_n8n_syntax(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return any(_n8n_syntax(v) for v in value)
    return False


def _scrub(value: Any) -> Any:
    """`value` with every n8n expression (or n8n-shaped object) left blank."""
    if isinstance(value, dict):
        if _N8N_OBJECT_KEYS & set(value):
            return ""
        return {k: _scrub(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub(v) for v in value]
    return "" if _n8n_syntax(value) else value


# --------------------------------------------------------------------------
# Slack channel names
# --------------------------------------------------------------------------

_SLACK_ID = re.compile(r"^[CGD][A-Z0-9]{8,}$")
_CHANNEL_TOKEN = re.compile(r"(?<![\w&/#])#([A-Za-z0-9][A-Za-z0-9_-]*)")
_HEX_COLOUR = re.compile(r"^([0-9a-f]{3}|[0-9a-f]{6})$", re.IGNORECASE)

# Sample keys whose "#..." value is a Slack channel. Anything else starting
# with "#" (an order or ticket number, a colour, a hashtag) is not.
_CHANNEL_KEYS = frozenset({
    "sent_to", "posted_to", "posted_in", "routed_to", "assigned_to", "escalated_to",
    "slack", "slack_posted",
})


def _channel_token(text: str) -> str:
    """The first `#name` in `text`, or "" when there is none or it is an
    order number (`#40911`) or a colour (`#ff5500`). "#sales - Marcus Reyes"
    gives "#sales"."""
    for match in _CHANNEL_TOKEN.finditer(str(text or "")):
        name = match.group(1).rstrip("-_")
        if not name or name.isdigit():
            continue
        if _HEX_COLOUR.match(name) and any(ch.isdigit() for ch in name):
            continue
        return "#" + name.lower()
    return ""


def _explicit_channel(value: Any) -> str:
    """An explicit spec channel, as written. A plain name gains its "#", a
    Slack channel id stays an id, a `{{...}}` Make mapping is kept, and an n8n
    `__rl` object gives its value (its cachedResultName when the value is an
    id). "" for anything that is not a usable string, including n8n syntax."""
    if isinstance(value, dict):
        if _N8N_OBJECT_KEYS & set(value) and "__rl" not in value:
            return ""
        raw = value.get("value")
        cached = value.get("cachedResultName")
        if isinstance(raw, str) and _SLACK_ID.match(raw.strip()) and isinstance(cached, str) and cached.strip():
            raw = cached
        elif not (isinstance(raw, str) and raw.strip()):
            raw = cached
        return _explicit_channel(raw) if isinstance(raw, str) else ""
    if not isinstance(value, str):
        return ""
    raw = value.strip()
    if not raw or _n8n_syntax(raw):
        return ""
    if raw.startswith("#") or raw.startswith("{{") or _SLACK_ID.match(raw):
        return raw
    return "#" + raw


def _is_channel_key(path: Tuple[str, ...]) -> bool:
    if not path:
        return False
    leaf = _raw_words(path[-1])
    if "channel" in leaf or "channels" in leaf or "_".join(leaf) in _CHANNEL_KEYS:
        return True
    # A map of channels: {"channel_map": {"ops": "#ops"}}.
    return len(path) > 1 and bool({"channel", "channels"} & set(_raw_words(path[-2])))


def _sample_channels(value: Any, path: Tuple[str, ...] = ()) -> List[Tuple[Tuple[str, ...], str]]:
    """Every channel a sample names under a channel key, with its key path."""
    found: List[Tuple[Tuple[str, ...], str]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            found += _sample_channels(child, path + (str(key),))
    elif isinstance(value, list):
        for child in value:
            found += _sample_channels(child, path)
    elif isinstance(value, str) and value.strip().startswith("#") and _is_channel_key(path):
        channel = _channel_token(value.strip())
        if channel:
            found.append((path, channel))
    return found


def _is_failure_word(word: str) -> bool:
    return word.startswith("fail") or word.startswith("error") or word in ("broke", "breaks", "broken")


def channel_name(label: str, section_label: str = "", params: Optional[Dict[str, Any]] = None,
                 notes: str = "", samples: Iterable[Any] = ()) -> str:
    """The Slack channel for a post step. The first source that gives one wins:

    1. the spec's own `params["channel"]` (or an n8n `channelId`/`channel`
       `__rl` object), emitted as written (`_explicit_channel`);
    2. a `#channel` named in the step label ("Notify #content");
    3. a `#channel` value in the samples under a channel-named key
       (`channel`, `slack_channel`, `sent_to`, `posted_to`, ...): the one whose
       key path shares a word with the label, else the only one there is,
       unless the step is about a failure;
    4. "#ops-alerts" when the label is about a failure or an error;
    5. "#general".

    `section_label` and `notes` are accepted for compatibility and not used:
    headline slugs and free-text mentions produced channels nobody asked for.
    """
    params = params or {}
    for key in ("channel", "channelId"):
        channel = _explicit_channel(params.get(key))
        if channel:
            return channel

    channel = _channel_token(label)
    if channel:
        return channel

    label_raw = _raw_words(_bare_label(label))
    failure = any(_is_failure_word(w) for w in label_raw)
    label_words = {_stem(w) for w in label_raw if w not in _STOP} - {"channel", "slack"}
    found: List[Tuple[Tuple[str, ...], str]] = []
    for sample in samples:
        found += _sample_channels(sample)
    best, best_score = "", 0
    for path, channel in found:
        path_words: Set[str] = set()
        for part in path:
            path_words |= _tokens(part)
        score = len((path_words - {"channel", "slack"}) & label_words)
        if score > best_score:
            best, best_score = channel, score
    if best:
        return best
    if len({c for _, c in found}) == 1 and not failure:
        return found[0][1]

    return "#ops-alerts" if failure else "#general"


_KEY_OK = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _ref(module_id: int, parts: Iterable[str]) -> str:
    """`{{1.card.name}}`; keys Make cannot parse bare go in backticks."""
    segs = [p if _KEY_OK.match(p) else "`{}`".format(p) for p in parts]
    return "{{%d.%s}}" % (module_id, ".".join(segs))


# --------------------------------------------------------------------------
# Sample fields -> mappable references
# --------------------------------------------------------------------------

# Leaf names that carry plumbing rather than content. They are still mapped
# when a label asks for them by name, just never picked as a fallback.
_NOISE = {"id", "event", "source", "action", "type", "ts", "version", "object", "kind"}
_PREFERRED = {"name", "email", "phone", "message", "text", "body", "subject",
              "title", "url", "link", "address", "company", "reason", "note"}

# Column-name synonyms, so an audit row's "item" finds a card or file name and
# its "source" finds the event that fired.
_SYNONYMS = {
    "source": {"event", "action", "origin", "channel"},
    "item": {"name", "title", "subject", "file", "card"},
    "status": {"state", "ok", "result"},
    # A board or folder name is what picks a team (and so its channel).
    "team": {"board", "folder", "department", "group"},
    "user": {"member", "owner", "uploaded", "assigned"},
    "who": {"member", "owner", "uploaded", "assigned"},
    "contact": {"email", "phone", "name"},
    "customer": {"name", "email", "customer"},
}


def _synonyms_of(words: Iterable[str]) -> Set[str]:
    """Stemmed synonyms for raw words, via `_SYNONYMS`. Only a plural is
    folded, so "contacted" (a yes/no flag) does not borrow `contact`'s name
    and email fields."""
    out: Set[str] = set()
    for word in words:
        for key in {word, word[:-1] if word.endswith("s") and len(word) > 3 else word}:
            out |= {_stem(s) for s in _SYNONYMS.get(key, ())}
    return out


class _Field(object):
    def __init__(self, path: Tuple[str, ...], value: Any, ref: str, index: int) -> None:
        self.path = path
        self.value = value
        self.ref = ref
        self.index = index
        self.leaf_tokens = _tokens(path[-1])
        self.parent_tokens: Set[str] = set()
        for part in path[:-1]:
            self.parent_tokens |= _tokens(part)
        raw = _raw_words(path[-1])
        # "name"/"url"/"id" alone say little; qualify them with their parent.
        if len(path) > 1 and (len(raw) == 1 and (raw[0] in _PREFERRED or raw[0] in _NOISE)):
            raw = _raw_words(path[-2]) + raw
        self.words = [w for w in raw if w not in ("by",)] or raw
        self.caption = " ".join(raw).capitalize()
        self.key = "_".join(raw)

    @property
    def is_noise(self) -> bool:
        leaf = "_".join(_raw_words(self.path[-1]))
        return (leaf in _NOISE or leaf.endswith("_at") or leaf.endswith("_id")
                or self.value in (None, ""))

    @property
    def is_preferred(self) -> bool:
        return bool({_stem(w) for w in _raw_words(self.path[-1])} & {_stem(p) for p in _PREFERRED})


class _Fields(object):
    """The trigger's output, flattened into mappable leaves."""

    def __init__(self, sample: Dict[str, Any], module_id: int = TRIGGER_ID,
                 prefix: Tuple[str, ...] = ()) -> None:
        self.leaves: List[_Field] = []
        self.module_id = module_id
        self.prefix = prefix
        self._flatten(sample or {}, (), 0)

    def _flatten(self, value: Any, path: Tuple[str, ...], depth: int) -> None:
        if isinstance(value, dict) and value and depth < 4:
            for key, child in value.items():
                self._flatten(child, path + (str(key),), depth + 1)
        elif path:
            ref = _ref(self.module_id, self.prefix + path)
            self.leaves.append(_Field(path, value, ref, len(self.leaves)))

    def __bool__(self) -> bool:
        return bool(self.leaves)

    __nonzero__ = __bool__

    def fallback(self, n: int) -> List[_Field]:
        good = [f for f in self.leaves if not f.is_noise and not isinstance(f.value, list)]
        good.sort(key=lambda f: (not f.is_preferred, f.index))
        rest = [f for f in self.leaves if f not in good]
        return (good + rest)[:n]

    @staticmethod
    def score(field: _Field, words: Set[str], synonyms: Set[str] = frozenset()) -> float:
        value = 2.0 * len(field.leaf_tokens & words) + 1.0 * len(field.parent_tokens & words)
        value += 1.0 * len(field.leaf_tokens & synonyms) + 0.5 * len(field.parent_tokens & synonyms)
        if value <= 0:
            return 0.0
        if field.is_preferred:
            value += 0.5
        if field.is_noise:
            value -= 0.5
        return max(value, 0.1)

    def pick(self, label: str, n: int = 3) -> List[_Field]:
        """Fields whose names (or their `_SYNONYMS`) the label mentions; the
        first meaningful ones if none. "Pick the Team Channel" finds the board
        name and the folder path this way."""
        words = _tokens(_bare_label(label))
        synonyms = _synonyms_of(_raw_words(_bare_label(label))) - words
        scored = [(self.score(f, words, synonyms), f) for f in self.leaves]
        hits = [f for s, f in sorted(scored, key=lambda sf: (-sf[0], sf[1].index)) if s > 0]
        if not hits:
            return self.fallback(n)
        if len(hits) < 2:
            hits += [f for f in self.fallback(n) if f not in hits]
        return hits[:n]


class _Output(object):
    """A module earlier on this branch whose result later steps can map."""

    def __init__(self, module_id: int, label: str, ref: str, kind: str, name: str = "") -> None:
        self.module_id = module_id
        self.name = name
        self.label = _bare_label(label)
        self.ref = ref
        self.kind = kind


# Real mapper field names per module, from verified exports. Spec params whose
# key is one of these land in the mapper; anything else keeps the old
# behaviour and merges into `parameters`.
_MAPPER_FIELDS = {
    "openai-gpt-3:CreateCompletion": {"select", "model", "messages", "max_tokens", "temperature",
                                      "n_completions", "response_format", "top_p"},
    "openai-gpt-3:transformTextToStructuredData": {"model", "text", "dataDefinition"},
    "slack:CreateMessage": {"channelType", "channel", "text", "parseType", "mrkdwn",
                            "thread_ts", "blocks", "username"},
    "google-sheets:addRow": {"mode", "from", "spreadsheetId", "sheetId", "values", "includesHeaders",
                             "insertDataOption", "valueInputOption", "insertUnformatted"},
    "google-sheets:updateRow": {"mode", "from", "spreadsheetId", "sheetId", "values", "rowNumber",
                                "includesHeaders", "valueInputOption"},
    "google-sheets:searchRows": {"mode", "from", "spreadsheetId", "sheetId", "includesHeaders",
                                 "limit", "filter", "sortOrder", "orderBy"},
    "airtable:ActionCreateRecord": {"base", "table", "record", "typecast", "useColumnId"},
    "airtable:ActionUpdateRecord": {"id", "base", "table", "record", "typecast", "useColumnId"},
    "airtable:ActionUpdateRecords": {"id", "base", "table", "record", "typecast", "useColumnId"},
    "airtable:ActionSearchRecords": {"base", "table", "fields", "formula", "maxRecords",
                                     "useColumnId", "sort", "view"},
    "http:ActionSendData": {"url", "method", "headers", "qs", "bodyType", "parseResponse",
                            "contentType", "data", "timeout", "shareCookies", "followRedirect",
                            "rejectUnauthorized", "serializeUrl", "useMtls", "gzip"},
    "util:SetVariable2": {"name", "scope", "value"},
    "google-email:ActionSendEmail": {"to", "cc", "bcc", "from", "subject", "html", "attachments"},
    "builtin:BasicFeeder": {"array"},
    "builtin:Sleep": {"delay"},
    "util:FunctionSleep": {"delay"},
}

# Keys in a sample row that describe where the row lives, not what is in it.
_ROW_META = {"sheet", "sheet_name", "spreadsheet", "row", "row_number", "tab", "table"}

_AI_TEXT_WORDS = {"message", "text", "summary", "body", "note", "sms", "email", "reply", "draft"}


def _client(spec: WorkflowSpec) -> Dict[str, Any]:
    raw = getattr(spec, "client", None)
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    return {k: getattr(raw, k, None) for k in ("name", "company", "industry", "location")}


# Spec params the Make compiler reads itself (the Make column of the params
# shorthand in skill/SKILL.md). An n8n expression in one of these is left
# blank and reported; it is never replaced by a generated value.
SHORTHAND_KEYS = frozenset({
    "prompt", "system_message", "url", "method", "headers", "body", "channel", "text",
    "columns", "document", "sheet", "to", "subject", "html", "cc", "bcc", "delay", "name",
    "value", "array",
})


def _clean_params(raw: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str], List[str]]:
    """(usable params, shorthand keys blanked, other keys dropped).

    A shorthand key holding n8n syntax stays, with the n8n parts blanked
    (`_scrub`). Any other key holding n8n syntax (raw n8n parameters such as
    `jsCode` or `options`) is dropped: Make cannot read it, so it never ships."""
    usable: Dict[str, Any] = {}
    blanked: List[str] = []
    dropped: List[str] = []
    for key, value in (raw or {}).items():
        if not _n8n_syntax(value):
            usable[key] = value
        elif key in SHORTHAND_KEYS:
            usable[key] = _scrub(value)
            blanked.append(key)
        elif not (key in ("channel", "channelId") and _explicit_channel(value)):
            dropped.append(key)
    return usable, blanked, dropped


def _given(p: Dict[str, Any], key: str) -> Tuple[bool, Any]:
    """(True, value) when the spec set `key`, even to a value blanked for
    holding n8n syntax; (False, None) when it did not. Pops the key."""
    value = p.pop(key, None)
    return value is not None, value


def _archetype_system_message(params: Optional[Dict[str, Any]]) -> str:
    """An archetype's own `options.systemMessage`, when it is plain text (an
    n8n expression that maps data cannot be carried over)."""
    options = (params or {}).get("options")
    text = options.get("systemMessage") if isinstance(options, dict) else None
    if not isinstance(text, str):
        return ""
    text = text[1:] if text.startswith("=") else text
    if "{{" in text or "$json" in text or "$(" in text:
        return ""
    return text.strip()


def _overview_text(spec: WorkflowSpec) -> str:
    raw = getattr(spec, "overview", None)
    if isinstance(raw, dict):
        items = raw.get("how_it_works") or []
        if isinstance(items, str):
            items = [items]
        return " ".join(str(i) for i in list(items)[:2])
    return str(raw or "")


def _json_text(pairs: List[Tuple[str, str]]) -> str:
    """A JSON-looking body whose values are Make references (kept unquoted-safe)."""
    lines = ['  "{}": "{}"'.format(k, v) for k, v in pairs]
    return "{\n" + ",\n".join(lines) + "\n}"


def _headers(value: Any) -> List[Dict[str, str]]:
    if isinstance(value, dict):
        return [{"name": str(k), "value": str(v)} for k, v in value.items()]
    if isinstance(value, list):
        return value
    return [{"name": "Authorization", "value": "Bearer {{YOUR_API_KEY}}"}]


# A row's status column is a route word, never a mapped field.
_STATUS_WORDS = frozenset({"status", "outcome", "result"})
# Status words a sample may carry that are constant on a success route.
_STATUS_LITERALS = frozenset({
    "ok", "success", "succeeded", "done", "complete", "completed", "posted", "sent",
    "delivered", "synced", "logged", "written", "saved", "created", "updated", "approved",
    "published", "drafted", "notified", "booked", "resolved", "processed", "received",
    "imported", "paid", "queued", "scheduled", "skipped", "escalated", "closed",
    "awaiting_approval", "needs_review", "needs review", "pending",
})
_NEGATIONS = frozenset({"no", "not", "nothing", "none", "without", "zero", "never"})
_SUCCESS_WORDS = frozenset({"ok", "okay", "success", "successful", "succeeded", "passed",
                            "completed", "complete", "worked", "posted", "sent", "delivered",
                            "synced", "clean"})


def _says_failure(text: str) -> Optional[bool]:
    """True when `text` is about a failure ("Did Anything Fail?", "error"),
    False when it is about success ("Posted OK?", "Completed Without
    Errors?", "nothing failed"), None when it says neither."""
    words = _raw_words(_bare_label(text))
    if any(_is_failure_word(w) for w in words):
        return not any(w in _NEGATIONS for w in words)
    if any(w in _SUCCESS_WORDS for w in words):
        return False
    return None


# `{{now}}` goes only in a column that records when the row was written.
_NOW_WORDS = frozenset({"timestamp", "datetime", "date", "logged", "when"})
_NOW_PARTNERS = _NOW_WORDS | frozenset({"run", "log", "event", "created", "sent", "submitted",
                                        "received", "processed"})
_NOT_NOW_WORDS = frozenset({
    "due", "next", "scheduled", "schedule", "expires", "expiry", "start", "starts", "end",
    "ends", "deadline", "follow", "until", "booked", "appointment", "meeting", "renewal",
    "close", "ms", "sec", "secs", "second", "seconds", "minute", "minutes", "min", "mins",
    "hour", "hours", "hr", "hrs", "day", "days", "duration", "elapsed", "latency", "saved",
    "estimate", "estimated", "spent", "taken", "to", "time",
})
_DATE_LIKE = re.compile(r"\d{4}-\d{2}-\d{2}|\d{1,2}[/.]\d{1,2}[/.]\d{2,4}")


def _is_now_column(words: List[str], sample: Any = None) -> bool:
    """"logged_at", "timestamp", "date", "When" -> True; durations, future
    times and references ("response_time_ms", "time_to_decision", "due_at",
    "logged_row") -> False, as is any column whose sample value is not a date."""
    if sample not in (None, "") and not (isinstance(sample, str) and _DATE_LIKE.search(sample)):
        return False
    if not words or set(words) & _NOT_NOW_WORDS:
        return False
    if words[-1] == "at" and len(words) > 1:
        return True
    return bool(set(words) & _NOW_WORDS) and set(words) <= _NOW_PARTNERS


# --------------------------------------------------------------------------
# Router route filters
# --------------------------------------------------------------------------

# The spec's condition ops, mirroring the n8n shorthand (params._SHORT_OPS) so
# one vocabulary works on both platforms. `eq`/`neq` pick number or text from
# `right`; `true`/`false` compare against a boolean (`_BOOL_B`).
_MAKE_OPS = {
    "exists": "exist", "not_exists": "notexist",
    "gt": "number:greater", ">": "number:greater",
    "gte": "number:greaterorequal", ">=": "number:greaterorequal",
    "lt": "number:less", "<": "number:less",
    "lte": "number:lessorequal", "<=": "number:lessorequal",
    "contains": "text:contain",
}
_EQ_OPS = frozenset({"eq", "==", "equals"})
_NEQ_OPS = frozenset({"neq", "!="})
_BOOL_OPS = {"true": True, "false": False}

# Make operator ids seen in real exports (make_blueprint_structures.md) and in
# integromat/make-skills skills/make-module-configuring/filtering.md @8ee0fef.
# make-skills blueprint-construction.md names `text:startswith` / `date:before`,
# which are wrong: the real ids are `text:startwith` / `date:less`. A raw id in
# `op` is passed through only when it is one of these.
_RAW_MAKE_OPS = frozenset({
    "exist", "notexist",
    "text:equal", "text:notequal", "text:equal:ci", "text:notequal:ci",
    "text:contain", "text:notcontain", "text:contain:ci", "text:notcontain:ci",
    "text:startwith", "text:startwith:ci", "text:endwith:ci",
    "text:pattern", "text:pattern:ci", "text:notpattern:ci",
    "number:equal", "number:notequal", "number:greater", "number:greaterorequal",
    "number:less", "number:lessorequal",
    "boolean:equal", "boolean:notequal",
    "array:contain", "array:notcontain", "array:contain:ci",
    "date:greater", "date:greaterorequal", "date:less", "date:lessorequal",
})
_UNARY_OPS = frozenset({"exist", "notexist"})
_BOOLEAN_OPS = frozenset({"boolean:equal", "boolean:notequal"})

# Operator -> its opposite, for the other arm of a two-way branch.
_NEGATION_PAIRS = (
    ("exist", "notexist"),
    ("text:equal", "text:notequal"),
    ("text:equal:ci", "text:notequal:ci"),
    ("number:equal", "number:notequal"),
    ("number:greater", "number:lessorequal"),
    ("number:less", "number:greaterorequal"),
    ("text:contain", "text:notcontain"),
    ("text:contain:ci", "text:notcontain:ci"),
    ("array:contain", "array:notcontain"),
)
_NEGATE = dict(_NEGATION_PAIRS)
_NEGATE.update((b, a) for a, b in _NEGATION_PAIRS)

# The `b` a boolean comparison ships with: Make's keyword in a string, as in
# real exports ({"a": "{{6.result.is_valid_invoice}}", "b": "{{true}}", "o":
# "boolean:equal"}) and make-skills filtering.md @8ee0fef.
_BOOL_B = {True: "{{true}}", False: "{{false}}"}

_NUMERIC = re.compile(r"^\s*-?\d+(\.\d+)?\s*$")
_BARE_MAPPING = re.compile(r"^\d+\.")
_TRUE_LABELS = frozenset({"true", "yes"})
_FALSE_LABELS = frozenset({"false", "no"})
_CONDITION_KINDS = frozenset({"flow.branch", "flow.switch"})


def _filter_value(right: Any) -> str:
    """A filter's `b`, as Make stores it. Numbers ship as JSON strings ("0",
    "200"), as in real exports."""
    if isinstance(right, bool):
        return _BOOL_B[right]
    if isinstance(right, (int, float)):
        return str(right)
    return "" if right is None else right


def _is_number(right: Any) -> bool:
    if isinstance(right, bool):
        return False
    if isinstance(right, (int, float)):
        return True
    return isinstance(right, str) and bool(_NUMERIC.match(right))


def _filter_left(left: Any) -> Tuple[Optional[str], str]:
    """(`a` in Make syntax, or None and why not)."""
    if left is None or (isinstance(left, str) and not left.strip()):
        return None, "missing left"
    if not isinstance(left, str):
        return None, "left {!r} is not a Make mapping".format(left)
    text = left.strip()
    if _N8N_EXPR.search(text):
        return None, "left {!r} is n8n syntax".format(left)
    if text.startswith("{{") and text.endswith("}}"):
        return text, ""
    if _BARE_MAPPING.match(text):
        return "{{%s}}" % text, ""
    return None, "left {!r} is not a Make mapping like {{{{5.statusCode}}}}".format(left)


def _filter_item(raw: Any) -> Tuple[Optional[Dict[str, Any]], str]:
    """One spec condition -> one Make filter condition, or None and why not."""
    if not isinstance(raw, dict):
        return None, "condition {!r} is not an object".format(raw)
    a, why = _filter_left(raw.get("left"))
    if a is None:
        return None, why
    op = str(raw.get("op", "")).strip()
    right = raw.get("right")
    if isinstance(right, str) and _N8N_EXPR.search(right):
        return None, "right {!r} is n8n syntax".format(right)
    if right is not None and not isinstance(right, (str, int, float, bool)):
        return None, "right {!r} is not a string or number".format(right)
    low = op.lower()
    if low in _BOOL_OPS:
        return {"a": a, "o": "boolean:equal", "b": _BOOL_B[_BOOL_OPS[low]]}, ""
    if low in _EQ_OPS or low in _NEQ_OPS:
        kind = "number" if _is_number(right) else "text"
        o = "{}:{}".format(kind, "equal" if low in _EQ_OPS else "notequal")
    elif low in _MAKE_OPS:
        o = _MAKE_OPS[low]
    elif op in _RAW_MAKE_OPS:
        o = op
    else:
        return None, "unknown op {!r}".format(op)
    if o in _UNARY_OPS:
        return {"a": a, "o": o}, ""
    return {"a": a, "o": o, "b": _filter_value(right)}, ""


def _filter_group(raw: Any) -> Tuple[Optional[List[Dict[str, Any]]], str]:
    """A condition (one object, or a list ANDed) -> one inner AND group."""
    items = raw if isinstance(raw, list) else [raw]
    if not items:
        return None, "empty condition"
    group: List[Dict[str, Any]] = []
    for item in items:
        built, why = _filter_item(item)
        if built is None:
            return None, why
        group.append(built)
    return group, ""


def _negated(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The opposite of one filter condition, or None when it has none."""
    o = item["o"]
    if o in _BOOLEAN_OPS:
        flipped = [flag for flag, b in _BOOL_B.items() if b == item.get("b")]
        if not flipped:
            return None
        return dict(item, b=_BOOL_B[not flipped[0]])
    if o not in _NEGATE:
        return None
    return dict(item, o=_NEGATE[o])


def _true_arm(edges: List[Any]) -> int:
    """Which of two edges takes the condition, as compile_n8n numbers them:
    the one labelled true/yes, else the other of one labelled false/no, else
    the first."""
    labels = [(e.branch or "").strip().lower() for e in edges]
    for i, label in enumerate(labels):
        if label in _TRUE_LABELS:
            return i
    for i, label in enumerate(labels):
        if label in _FALSE_LABELS:
            return 1 - i
    return 0


class _Builder(object):
    def __init__(self, spec: WorkflowSpec, catalog: Catalog) -> None:
        self.spec = spec
        self.catalog = catalog
        self.next_id = 1
        self.emitted: Dict[str, int] = {}
        self.fields = _Fields(spec.input_sample)
        self.section_first: Dict[str, int] = {}
        self.outputs: List[_Output] = []
        self.sections = {s.key: s for s in spec.sections}
        self.client = _client(spec)
        # (node key, branch taken out of it) for every step on the branch being
        # emitted, so a status column can tell a failure route from a success
        # route (`_route_state`).
        self.route: List[Tuple[str, Optional[str]]] = []
        # Spec params that held n8n syntax and were left blank, as
        # "<label> (<key>)", for the compile warnings.
        self.unresolved: List[str] = []
        # Raw (non-shorthand) params dropped for holding n8n syntax.
        self.dropped: List[str] = []
        # Router routes whose spec condition could not become a filter, as
        # "<label> (<reason>)"; those routes keep the placeholder filter.
        self.route_warnings: List[str] = []
        # Set-variable value -> the label that first used it, so two different
        # steps never show the same value on camera.
        self.var_values: Dict[str, str] = {}

    def may_emit(self, key: str, path: Set[str]) -> bool:
        return key not in path and self.emitted.get(key, 0) < MAX_COPIES

    def mark(self, key: str) -> None:
        self.emitted[key] = self.emitted.get(key, 0) + 1

    def take_id(self) -> int:
        value = self.next_id
        self.next_id += 1
        return value

    # -- module construction ----------------------------------------------

    def module_for(self, node: Node, x: int, y: int,
                   upstream: Optional[List[_Output]] = None,
                   is_entry: bool = False) -> Dict[str, Any]:
        resolution = self.catalog.resolve(node)
        entry = resolution.entry
        module_name = entry.get("module", "")
        params = dict(entry.get("parameters", {}))

        module: Dict[str, Any] = {
            "id": self.take_id(),
            "module": module_name,
            "version": entry.get("version", 1),
            "parameters": params,
            "mapper": {},
            "metadata": {
                "designer": {"x": x, "y": y, "name": node.label},
                "restore": {},
            },
        }
        if module_name == "http:ActionSendData" and node.app:
            slug = "".join(ch for ch in node.app.lower() if ch.isalnum())
            path = (node.op or "records").replace("_", "-")
            module["mapper"] = {
                "url": "https://api.{}.com/v1/{}".format(slug, path),
                "method": "post",
            }

        spec_params, blanked, dropped = _clean_params(node.params or {})
        label = _ascii(node.label)
        self.unresolved += ["{} ({})".format(label, key) for key in blanked]
        self.dropped += ["{} ({})".format(label, key) for key in dropped]
        mapper, extra_meta = self.mapper_defaults(
            module_name, node, module["mapper"], spec_params,
            list(upstream if upstream is not None else self.outputs), is_entry,
        )
        # Whatever the defaults did not consume: real mapper names go to the
        # mapper (spec wins), everything else merges into parameters as before.
        known = _MAPPER_FIELDS.get(module_name, set())
        for key, value in spec_params.items():
            default = mapper.get(key)
            same_shape = default is None or isinstance(value, type(default)) or (
                isinstance(default, str) and isinstance(value, (int, float)))
            if key in known and same_shape:
                mapper[key] = value
            else:
                params[key] = value
        module["mapper"] = mapper
        module["metadata"].update(extra_meta)

        if node.section and node.section not in self.section_first:
            self.section_first[node.section] = module["id"]
        return module

    def output_of(self, module: Dict[str, Any], node: Node, is_entry: bool) -> Optional[_Output]:
        name = module.get("module", "")
        mid = module["id"]
        if is_entry:
            return None
        if name.startswith("util:SetVariable2"):
            var = module.get("mapper", {}).get("name") or "value"
            return _Output(mid, node.label, _ref(mid, [var]), "var", var)
        if name.startswith("openai-gpt-3:"):
            return _Output(mid, node.label, _ref(mid, ["result"]), "ai")
        if name.startswith("http:ActionSendData"):
            return _Output(mid, node.label, _ref(mid, ["data"]), "http")
        if name.startswith("airtable:ActionSearchRecords") or name.startswith("airtable:ActionCreateRecord"):
            return _Output(mid, node.label, _ref(mid, ["id"]), "record")
        return None

    def set_variable(self, label: str, value: Any, x: int, y: int) -> Dict[str, Any]:
        special = self.catalog.special.get("set_variable", {})
        return {
            "id": self.take_id(),
            "module": special.get("module", "util:SetVariable2"),
            "version": special.get("version", 1),
            "parameters": {"scope": "roundtrip"},
            "mapper": {
                "name": label.lower().replace(" ", "_"),
                "scope": "roundtrip",
                "value": json.dumps(value, indent=2, ensure_ascii=False),
            },
            "metadata": {
                "designer": {"x": x, "y": y, "name": label},
                "restore": {},
            },
        }

    # -- mapper synthesis --------------------------------------------------

    def _lines(self, fields: List[_Field]) -> List[str]:
        return ["{}: {}".format(f.caption, f.ref) for f in fields]

    def _last(self, upstream: List[_Output], kinds: Tuple[str, ...]) -> Optional[_Output]:
        for out in reversed(upstream):
            if out.kind in kinds:
                return out
        return None

    def system_prompt(self, node: Node) -> str:
        company = _ascii(self.client.get("company") or self.client.get("name") or "")
        industry = _ascii(self.client.get("industry") or "")
        title = _ascii(self.spec.title)
        owner = "{}'s".format(company) if company else "the"
        opener = 'You handle one step of {} "{}" automation{}. This step: {}.'.format(
            owner, title,
            " for a {} business".format(industry.lower()) if industry else "",
            _bare_label(node.label),
        )
        parts = [opener]
        section = self.sections.get(node.section or "")
        if section and section.note:
            parts.append("Context: {}".format(_ascii(section.note)))
        if node.notes:
            parts.append("Rules for this step: {}".format(_ascii(node.notes)))
        overview = _ascii(_overview_text(self.spec))
        if overview:
            parts.append("What the whole system is for: {}".format(overview[:400]))
        parts.append("Work only from the fields in the user message. Never invent names, "
                     "prices, dates or links. Return only the requested output, with no preamble.")
        return "\n\n".join(parts)

    def _user_message(self, node: Node, upstream: List[_Output]) -> str:
        lines = self._lines(self.fields.pick(node.label, 5))
        prior = self._last(upstream, ("ai", "var", "http"))
        if prior:
            lines.append("{}: {}".format(prior.label, prior.ref))
        return "\n".join(lines) or _bare_label(node.label)

    def _columns(self, node: Node, spec_columns: Any) -> Tuple[List[str], Dict[str, Any], str]:
        """(column names, explicit values, block name) for a row-writing step."""
        if isinstance(spec_columns, dict):
            return [str(k) for k in spec_columns], dict(spec_columns), ""
        if isinstance(spec_columns, (list, tuple)) and spec_columns:
            return [str(c) for c in spec_columns], {}, ""
        words = _tokens(_bare_label(node.label)) | {"row", "log", "record", "audit", "entry", "sheet"}
        best: Tuple[float, str, Dict[str, Any]] = (0.0, "", {})
        for key, value in (self.spec.output_sample or {}).items():
            if isinstance(value, dict) and value and all(not isinstance(v, dict) for v in value.values()):
                score = len(_tokens(key) & words)
                if score > best[0]:
                    best = (float(score), key, value)
        if best[1]:
            cols = [k for k in best[2] if k.lower() not in _ROW_META]
            return cols[:8], {}, best[1]
        scalars = [k for k, v in (self.spec.output_sample or {}).items()
                   if not isinstance(v, (dict, list))]
        if len(scalars) >= 2:
            return scalars[:8], {}, ""
        return [f.key for f in self.fields.fallback(6)], {}, ""

    def _exact_ref(self, key: str, upstream: List[_Output]) -> str:
        """The reference whose name is exactly the column's name: a set-variable
        earlier on this branch named `key`, else a trigger field whose leaf,
        parent-qualified name or full path is `key`. "" when there is none, or
        when only bare leaves match and there are several ("name" with both
        card.name and board.name in the sample)."""
        for out in reversed(upstream):
            if out.kind == "var" and out.name == key:
                return out.ref
        leaves: List[str] = []
        for f in self.fields.leaves:
            full = "_".join(w for part in f.path for w in _raw_words(part))
            if key in (f.key, full):
                return f.ref
            if key == "_".join(_raw_words(f.path[-1])):
                leaves.append(f.ref)
        return leaves[0] if len(leaves) == 1 else ""

    def _route_state(self) -> Optional[str]:
        """"failed" or "ok" when the branch being emitted says so, else None.

        Only the route actually taken counts: the branch names on the edges
        walked to get here. A true/false (yes/no) branch
        is read against its gate's question ("Did X Fail?" true = failed,
        "Completed Without Errors?" true = ok); a gate whose question says
        neither leaves the state unknown. The latest decisive branch wins."""
        state: Optional[str] = None
        for key, branch in self.route:
            if not branch:
                continue
            words = _raw_words(branch)
            if words in (["true"], ["yes"], ["false"], ["no"]):
                asks = _says_failure(self.spec.node(key).label)
                if asks is None:
                    continue
                failed = asks if words[0] in ("true", "yes") else not asks
            else:
                failed = _says_failure(branch)
                if failed is None:
                    continue
            state = "failed" if failed else "ok"
        return state

    def _status_value(self, sample: Any) -> str:
        """A status column: "failed" on a failure route, the sample's status
        word on a success route (when it is one of `_STATUS_LITERALS`), and
        blank whenever the route does not settle it."""
        state = self._route_state()
        if state == "failed":
            return "failed"
        if state == "ok" and isinstance(sample, str) and sample.strip().lower() in _STATUS_LITERALS:
            return _ascii(sample.strip())
        return ""

    def _row_values(self, columns: List[str], explicit: Dict[str, Any], sample_block: Dict[str, Any],
                    upstream: List[_Output]) -> List[str]:
        """One value per column, and nothing is guessed:

        * an explicit spec value (`columns` as an object) as written;
        * a status column (`_status_value`);
        * a set-variable or trigger field with exactly the column's name;
        * `{{now}}` for a column that records when the row was written;
        * otherwise blank. Sample values never stand in for a mapping.

        Each reference goes to at most one column."""
        values: List[str] = []
        used: Set[str] = set()
        for col in columns:
            key = "_".join(_raw_words(col))
            words = key.split("_")
            if col in explicit:
                value = "" if explicit[col] is None else str(explicit[col])
            elif set(words) & _STATUS_WORDS:
                value = self._status_value(sample_block.get(col))
            else:
                value = self._exact_ref(key, upstream)
                if value in used:
                    value = ""
                if not value and _is_now_column(words, sample_block.get(col)):
                    value = "{{now}}"
            if value.startswith("{{") and value != "{{now}}":
                used.add(value)
            values.append(value)
        return values

    def _row(self, node: Node, spec_params: Dict[str, Any], upstream: List[_Output]) -> Tuple[List[str], List[str], str]:
        columns, explicit, block = self._columns(node, spec_params.pop("columns", None))
        out_sample = self.spec.output_sample or {}
        sample_block = out_sample.get(block, {}) if block else out_sample
        if not isinstance(sample_block, dict):
            sample_block = {}
        values = self._row_values(columns, explicit, sample_block, upstream)
        sheet_in_sample = next((str(v) for k, v in sample_block.items()
                                if k.lower() in ("sheet", "sheet_name", "tab", "table")
                                and isinstance(v, str) and v), "")
        if sheet_in_sample:
            return [_ascii(c) for c in columns], values, _ascii(sheet_in_sample)[:60]
        name = block or _bare_label(node.label)
        name = re.sub(r"\b(row|rows|record|records)\b", "log", name.replace("_", " "), flags=re.I)
        return [_ascii(c) for c in columns], values, _ascii(name).title()[:60]

    def mapper_defaults(self, module_id: str, node: Node, mapper: Dict[str, Any],
                        p: Dict[str, Any], upstream: List[_Output],
                        is_entry: bool) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Fill every required field Make can validate without an account, so the
        imported scenario shows warnings only where a connection or webhook has to be
        picked. An empty module renders a red triangle on camera; a filled one does
        not, even with no connection attached yet.

        `p` is the node's spec params; shorthand keys are consumed here (they
        win over the synthesised values), the rest are routed by the caller."""
        label = _bare_label(node.label)
        m = dict(mapper)
        meta: Dict[str, Any] = {}
        picked = self.fields.pick(node.label, 3) if not is_entry else []

        if module_id.startswith("openai-gpt-3:CreateCompletion"):
            given, system = _given(p, "system_message")
            if not given:
                system = _archetype_system_message(node.params) or self.system_prompt(node)
            given, user = _given(p, "prompt")
            if not given:
                user = self._user_message(node, upstream)
            m.setdefault("select", "chat")
            m.setdefault("model", "gpt-4.1")
            m["messages"] = [
                {"role": "system", "content": _ascii(system)},
                {"role": "user", "content": user},
            ]
            m.setdefault("max_tokens", "800")
            m.setdefault("temperature", "0.3")
            m.setdefault("n_completions", "1")
            m.setdefault("response_format", "text")
        elif module_id.startswith("openai-gpt-3:transformTextToStructuredData"):
            m.setdefault("model", "gpt-4.1")
            given, text = _given(p, "prompt")
            m["text"] = text if given else self._user_message(node, upstream)
            p.pop("system_message", None)
            m.setdefault("dataDefinition", [{"key": "result", "description": label}])
        elif module_id.startswith("slack:CreateMessage"):
            section = self.sections.get(node.section or "")
            channel = channel_name(
                node.label, section.label if section else "",
                params=dict(node.params or {}, channel=p.pop("channel", None)),
                notes=node.notes or "",
                samples=(self.spec.output_sample, self.spec.input_sample),
            )
            given, text = _given(p, "text")
            if not given:
                lines = ["*{}*".format(label)] + self._lines(picked)
                draft = self._last(upstream, ("ai",))
                if draft:
                    lines.append("{}: {}".format(draft.label, draft.ref))
                text = "\n".join(lines)
            m.setdefault("channelType", "public")
            m["channel"] = channel
            m["text"] = text
            m.setdefault("parseType", "full")
            m.setdefault("mrkdwn", True)
        elif module_id.startswith("google-sheets:addRow") or module_id.startswith("google-sheets:updateRow"):
            document = p.pop("document", None)
            given, sheet = _given(p, "sheet")
            columns, values, sheet_name = self._row(node, p, upstream)
            m.setdefault("mode", "select")
            if module_id.startswith("google-sheets:addRow"):
                m.setdefault("insertDataOption", "INSERT_ROWS")
            else:
                m.setdefault("rowNumber", "2")
            m.setdefault("valueInputOption", "USER_ENTERED")
            m.setdefault("includesHeaders", True)
            m["spreadsheetId"] = document or ""
            m["sheetId"] = sheet if given else sheet_name
            m["values"] = {str(i): v for i, v in enumerate(values)}
            # Column captions for the editor. Make rebuilds `expect` from the
            # live sheet once a connection is picked; until then this is what
            # shows beside each value. The `values` collection shape matches
            # 47 of 50 real addRow exports in the review corpus.
            values_spec = {
                "name": "values", "type": "collection", "label": "Values",
                "spec": [{"name": str(i), "type": "text",
                          "label": "{} ({})".format(c, chr(65 + i) if i < 26 else i)}
                         for i, c in enumerate(columns)],
            }
            meta["expect"] = [values_spec]
            if module_id.startswith("google-sheets:addRow"):
                # Real exports also carry the captions under
                # restore.expect.includesHeaders: {"label": "Yes", "nested":
                # [<values collection>]} in 44 of 50 addRow modules in the
                # review corpus, one shape throughout (e.g. f45.json, f109.json).
                meta["restore"] = {"expect": {"includesHeaders": {
                    "label": "Yes", "nested": [dict(values_spec)]}}}
        elif module_id.startswith("google-sheets:searchRows"):
            m.setdefault("mode", "select")
            m["spreadsheetId"] = p.pop("document", None) or ""
            m["sheetId"] = p.pop("sheet", None) or label.title()[:60]
            m.setdefault("includesHeaders", True)
            m.setdefault("limit", "1")
        elif module_id.startswith("airtable:ActionSearchRecords"):
            m["base"] = p.pop("document", None) or ""
            m["table"] = p.pop("sheet", None) or label.title()[:60]
            if picked:
                m.setdefault("formula", '{%s} = "%s"' % (picked[0].caption, picked[0].ref))
            m.setdefault("maxRecords", "1")
            m.setdefault("useColumnId", False)
        elif module_id.startswith("airtable:ActionCreateRecord") or module_id.startswith("airtable:ActionUpdateRecord"):
            document = p.pop("document", None)
            sheet = p.pop("sheet", None)
            columns, values, table = self._row(node, p, upstream)
            if module_id.startswith("airtable:ActionUpdateRecord"):
                found = self._last(upstream, ("record",))
                m.setdefault("id", found.ref if found else "")
            m["base"] = document or ""
            m["table"] = sheet or table
            m["record"] = dict(zip(columns, values))
            m.setdefault("typecast", False)
            m.setdefault("useColumnId", False)
        elif module_id.startswith("http:ActionSendData"):
            given, url = _given(p, "url")
            if given:
                m["url"] = url
            m["method"] = str(p.pop("method", None) or m.get("method") or "post").lower()
            m["headers"] = _headers(p.pop("headers", None))
            m.setdefault("qs", [])
            m.setdefault("bodyType", "raw")
            m.setdefault("parseResponse", True)
            m.setdefault("contentType", "application/json")
            body = p.pop("body", None)
            if body is not None:
                m["data"] = body if isinstance(body, str) else json.dumps(body, indent=2)
            elif is_entry:
                m.setdefault("data", "")
            else:
                pairs = [(f.key, f.ref) for f in picked]
                prior = self._last(upstream, ("ai", "var"))
                if prior and prior.kind == "ai":
                    pairs.append(("message", prior.ref))
                m["data"] = _json_text(pairs) if pairs else ""
            m.setdefault("timeout", "")
            m.setdefault("shareCookies", False)
            m.setdefault("followRedirect", True)
            m.setdefault("rejectUnauthorized", True)
        elif module_id.startswith("util:SetVariable2"):
            name = "_".join(_raw_words(label))[:60] or "step"
            m.setdefault("name", name)
            m.setdefault("scope", "roundtrip")
            m.setdefault("value", self._variable_value(label, upstream, _ascii(node.label)))
        elif module_id.startswith("google-email:ActionSendEmail"):
            email = [f for f in self.fields.leaves if "email" in _raw_words(f.path[-1])]
            m.setdefault("to", [email[0].ref] if email else [])
            m.setdefault("subject", label)
            body = self._last(upstream, ("ai",))
            m.setdefault("html", body.ref if body else "<br>".join(self._lines(picked)))
            m.setdefault("cc", [])
            m.setdefault("bcc", [])
            m.setdefault("attachments", [])
        elif module_id.startswith("gateway:CustomWebHook"):
            m.setdefault("maxResults", 1)
        elif module_id.startswith("util:Sleep") or module_id.startswith("builtin:Sleep"):
            m.setdefault("delay", "300")
        elif module_id.startswith("builtin:BasicFeeder"):
            arrays = [f for f in self.fields.leaves if isinstance(f.value, list)]
            words = _tokens(label)
            arrays.sort(key=lambda f: (-_Fields.score(f, words), f.index))
            if arrays:
                m.setdefault("array", arrays[0].ref)
            elif picked:
                m.setdefault("array", picked[0].ref)
        elif module_id.startswith("builtin:BasicRouter"):
            pass
        return m, meta

    def _variable_value(self, label: str, upstream: List[_Output], owner: str = "") -> str:
        """A set-variable's value from the fields its label names (synonyms
        included). A step with a different label never repeats an earlier
        step's value byte for byte: the latest upstream result is added, then
        the next fields along, until it reads as its own step."""
        as_text = bool(_tokens(label) & _AI_TEXT_WORDS)
        pairs = [(f.caption if as_text else f.key, f.ref) for f in self.fields.pick(label, 5)]

        def render(items: List[Tuple[str, str]]) -> str:
            if not items:
                return ""
            if as_text:
                return "\n".join("{}: {}".format(k, v) for k, v in items)
            return _json_text(items)

        attempts = [pairs]
        refs = {ref for _, ref in pairs}
        prior = [o for o in reversed(upstream) if o.kind in ("var", "ai", "http") and o.ref not in refs]
        if prior:
            key = prior[0].label if as_text else "_".join(_raw_words(prior[0].label))[:40]
            attempts.append(pairs + [(key, prior[0].ref)])
        spare = [f for f in self.fields.fallback(len(self.fields.leaves)) if f.ref not in refs]
        for start in range(0, len(spare), 2):
            extra = [(f.caption if as_text else f.key, f.ref) for f in spare[start:start + 2]]
            attempts.append(attempts[-1] + extra)
        # Last resort, when the sample is too small to tell the steps apart:
        # say which step this is.
        # `owner` is the full step label: "4c - Credit the Owner" and "4d -
        # Credit the Owner" are different steps with the same bare label.
        owner = owner or label
        attempts.append(attempts[-1] + [("Step" if as_text else "step", owner)])
        value = render(pairs)
        for items in attempts:
            value = render(items)
            if self.var_values.get(value, owner) == owner:
                break
        self.var_values.setdefault(value, owner)
        return value

    # -- graph walking -----------------------------------------------------

    def emit(self, node: Node, x: int, y: int, upstream: List[_Output],
             is_entry: bool = False) -> Tuple[Dict[str, Any], List[_Output]]:
        module = self.module_for(node, x, y, upstream, is_entry)
        out = self.output_of(module, node, is_entry)
        if out is not None:
            self.outputs.append(out)
            upstream = upstream + [out]
        return module, upstream

    def route_warn(self, node: Node, reason: str) -> None:
        line = "{} ({})".format(_ascii(node.label) or node.key, reason)
        if line not in self.route_warnings:
            self.route_warnings.append(line)

    def route_filters(self, node: Node, edges: List[Any]) -> List[Optional[List[List[Dict[str, Any]]]]]:
        """Each route's filter `conditions`, or None for the stand-in.

        An edge's own `condition` wins. Otherwise a flow.branch/flow.switch
        `params.condition` covers a two-way split: the true arm (`_true_arm`)
        gets it and the other arm its negation, an OR of each negated item.
        Anything that cannot be carried exactly is warned about and left to
        the stand-in; no operator is guessed."""
        filters: List[Optional[List[List[Dict[str, Any]]]]] = [None] * len(edges)
        params = node.params or {}
        node_condition = params.get("condition") if node.kind in _CONDITION_KINDS else None
        for i, edge in enumerate(edges):
            if edge.condition is None:
                continue
            group, why = _filter_group(edge.condition)
            if group is None:
                self.route_warn(node, "route {!r}: {}".format(edge.branch or edge.dst, why))
            else:
                filters[i] = [group]
        pending = [i for i, edge in enumerate(edges) if edge.condition is None]
        if node_condition is None or not pending:
            return filters
        if len(edges) != 2:
            self.route_warn(node, "{} routes: put `condition` on each edge".format(len(edges)))
            return filters
        group, why = _filter_group(node_condition)
        if group is None:
            self.route_warn(node, why)
            return filters
        true_index = _true_arm(edges)
        if true_index in pending:
            filters[true_index] = [group]
        other = 1 - true_index
        if other in pending:
            negated = [_negated(item) for item in group]
            if any(item is None for item in negated):
                self.route_warn(node, "no opposite for the other route: put `condition` on each edge")
            else:
                filters[other] = [[item] for item in negated]
        return filters

    def walk(self, start: str, x: int, y: int,
             path: Optional[Set[str]] = None,
             upstream: Optional[List[_Output]] = None,
             route: Optional[List[Tuple[str, Optional[str]]]] = None) -> Tuple[List[Dict[str, Any]], int]:
        """Emit a linear chain from `start`, nesting routers as they appear.

        `path` holds the keys already on this branch, which keeps a shared tail
        from being walked into itself. Nodes seen on a *different* branch are
        re-emitted deliberately: a router route with nothing in it renders as a
        branch leading nowhere, which looks broken on camera. `upstream` is what
        this branch has produced so far, for mapping later steps onto it;
        `route` is the (key, branch) trail that led here (`_route_state`).
        """
        path = set(path or ())
        route = list(route or [])
        upstream = list(upstream or [])
        flow: List[Dict[str, Any]] = []
        key: Optional[str] = start
        cursor = x

        while key is not None and self.may_emit(key, path):
            path.add(key)
            self.mark(key)
            node = self.spec.node(key)
            edges = self.spec.successors(key)

            if len(edges) <= 1:
                self.route = route
                module, upstream = self.emit(node, cursor, y, upstream)
                self.route = []
                flow.append(module)
                cursor += X_STEP
                route = route + [(key, edges[0].branch if edges else None)]
                key = edges[0].dst if edges else None
                continue

            # Fan-out becomes a router; each branch is walked into its own
            # nested flow and labelled with a filter carrying the branch name.
            router_entry = self.catalog.special.get("router", {})
            router = {
                "id": self.take_id(),
                "module": router_entry.get("module", "builtin:BasicRouter"),
                "version": router_entry.get("version", 1),
                "mapper": None,
                "metadata": {"designer": {"x": cursor, "y": y, "name": node.label}},
                "routes": [],
            }
            if node.section and node.section not in self.section_first:
                self.section_first[node.section] = router["id"]
            cursor += X_STEP
            filters = self.route_filters(node, edges)
            for i, edge in enumerate(edges):
                branch_y = y + (i - (len(edges) - 1) / 2.0) * ROUTE_Y_STEP
                branch_flow, _ = self.walk(edge.dst, cursor, int(branch_y), path, upstream,
                                           route + [(key, edge.branch)])
                if not branch_flow:
                    # Nothing left to draw down this arm — a labelled no-op beats
                    # an empty route, which reads as an unfinished scenario.
                    branch_flow = [
                        self.set_variable(
                            edge.branch.title() if edge.branch else "Continue",
                            {"branch": edge.branch or "continue"},
                            cursor,
                            int(branch_y),
                        )
                    ]
                if filters[i] is not None:
                    branch_flow[0]["filter"] = {
                        "name": edge.branch.title() if edge.branch else "",
                        "conditions": filters[i],
                    }
                elif edge.branch:
                    # No usable spec condition: a stand-in that names the
                    # route. `exist` is unary — real exports omit `b` entirely
                    # for it, and the operator is `exist`, not `exists`.
                    branch_flow[0]["filter"] = {
                        "name": edge.branch.title(),
                        "conditions": [[{"a": "{{%s.value}}" % router["id"],
                                         "o": "exist"}]],
                    }
                router["routes"].append({"flow": branch_flow})
            flow.append(router)
            return flow, cursor

        return flow, cursor


def _tail_of(flow: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Where a trailing module belongs, and what it follows.

    Nothing can sit after a router at the same level — in Make, a router is
    terminal and everything downstream lives inside one of its routes. So a
    trailing module descends into the primary route instead of being appended
    where it would produce a blueprint the editor cannot render.
    """
    if not flow:
        return flow, None
    last = flow[-1]
    routes = last.get("routes")
    if routes:
        primary = routes[0]["flow"]
        if not primary:
            return primary, last
        return _tail_of(primary)
    return flow, last


def _after(anchor: Optional[Dict[str, Any]]) -> Tuple[int, int]:
    if not anchor:
        return 0, 0
    designer = anchor.get("metadata", {}).get("designer", {})
    return int(designer.get("x", 0)) + X_STEP, int(designer.get("y", 0))


def _notes(builder: _Builder) -> List[Dict[str, Any]]:
    """One canvas note per section, pinned to the section's first module."""
    notes: List[Dict[str, Any]] = []
    for section in builder.spec.sections:
        module_id = builder.section_first.get(section.key)
        label, text = _ascii(section.label), _ascii(section.note)
        if module_id is None or not (label or text):
            continue
        content = ""
        if label:
            content += "<p><strong>{}</strong></p>".format(html.escape(label, quote=False))
        if text:
            content += "<p>{}</p>".format(html.escape(text, quote=False))
        notes.append({
            "moduleIds": [module_id],
            "content": content,
            "isFilterNote": False,
            "metadata": {"color": NOTE_COLOR},
        })
    return notes


def compile_make_with_warnings(spec: WorkflowSpec,
                               catalog: Optional[Catalog] = None) -> Tuple[Dict[str, Any], List[str]]:
    """(blueprint, warnings). Warnings list what the blueprint could not
    carry: spec params left blank because they held n8n syntax, and raw n8n
    params not shipped."""
    catalog = catalog or get_catalog("make", fresh=True)
    builder = _Builder(spec, catalog)
    warnings: List[str] = []

    entry_node = spec.entry_node()
    flow: List[Dict[str, Any]] = []
    cursor = 0

    # Trigger first, then the Sample Input stand-in for pinned data.
    builder.mark(entry_node.key)
    instant = True
    if entry_node.kind == "trigger.schedule":
        instant = False
    trigger, upstream = builder.emit(entry_node, cursor, 0, [], is_entry=True)
    flow.append(trigger)
    cursor += X_STEP
    if trigger.get("module", "").startswith("http:"):
        # A polling trigger returns the payload under `data`, not at the top.
        builder.fields = _Fields(spec.input_sample, TRIGGER_ID, ("data",))

    if spec.input_sample:
        flow.append(builder.set_variable("Sample Input", spec.input_sample, cursor, 0))
        cursor += X_STEP

    successors = spec.successors(entry_node.key)
    if successors:
        body, cursor = builder.walk(successors[0].dst, cursor, 0, {entry_node.key}, upstream)
        flow.extend(body)

    # Anything unreachable from the trigger still deserves to appear, so a
    # partially-wired spec does not silently lose nodes. Any second trigger (a
    # business trigger, or an n8n error trigger) stays in the chain on
    # purpose: Make runs one scenario per webhook, and the proposal says so
    # (skill/SKILL.md).
    for node in spec.flow_nodes:
        if not builder.emitted.get(node.key):
            builder.mark(node.key)
            target, anchor = _tail_of(flow)
            x, y = _after(anchor)
            builder.route = []
            module, _ = builder.emit(node, x, y, list(builder.outputs))
            target.append(module)
    if spec.output_sample:
        target, anchor = _tail_of(flow)
        x, y = _after(anchor)
        target.append(builder.set_variable("Final Output", spec.output_sample, x, y))

    if builder.unresolved:
        warnings.append("make: n8n expressions left blank (rewrite as {{1.field}} or fill on camera): "
                        + "; ".join(builder.unresolved))
    if builder.dropped:
        warnings.append("make: raw n8n params with n8n expressions not shipped: "
                        + "; ".join(builder.dropped))
    if builder.route_warnings:
        warnings.append("make: route conditions not applied (those routes keep the placeholder "
                        "filter; fix on camera): " + "; ".join(builder.route_warnings))

    blueprint = {
        "name": spec.title,
        "flow": flow,
        "metadata": {
            "instant": instant,
            "version": 1,
            "scenario": {
                "roundtrips": 1,
                "maxErrors": 3,
                "autoCommit": True,
                "autoCommitTriggerLast": True,
                "sequential": False,
                "slots": None,
                "confidential": False,
                "dataloss": False,
                "dlq": False,
                "freshVariables": False,
            },
            "designer": {"orphans": []},
            "zone": "us1.make.com",
            "notes": _notes(builder),
        },
    }
    return blueprint, warnings


def compile_make(spec: WorkflowSpec, catalog: Optional[Catalog] = None) -> Dict[str, Any]:
    """The Make blueprint. Its warnings (`compile_make_with_warnings`) are
    also added to `catalog.report()`, which is how the build pipeline shows
    catalog warnings, so they reach the build result without a new field."""
    catalog = catalog or get_catalog("make", fresh=True)
    blueprint, warnings = compile_make_with_warnings(spec, catalog)
    _add_to_report(catalog, warnings)
    return blueprint


def _add_to_report(catalog: Catalog, warnings: List[str]) -> None:
    extra = getattr(catalog, "make_warnings", None)
    if extra is None:
        extra = []
        base_report = catalog.report
        setattr(catalog, "make_warnings", extra)
        setattr(catalog, "report", lambda: base_report() + list(extra))
    extra[:] = warnings


def to_json(spec: WorkflowSpec, catalog: Optional[Catalog] = None) -> str:
    return json.dumps(compile_make(spec, catalog), indent=2, ensure_ascii=False)
