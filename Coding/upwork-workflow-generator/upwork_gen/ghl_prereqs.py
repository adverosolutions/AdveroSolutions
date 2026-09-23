"""Create the GoHighLevel objects a GHL spec needs, so import has no hand steps.

    python3 -m upwork_gen.ghl_prereqs <spec.json> [--apply] [--location <id>]

Reads the spec, works out every tag, pipeline (with ordered stages), contact
custom field and custom value it references, compares that with the
sub-account over the GHL REST API, and prints a plan. With --apply it creates
only what is missing, then reads the account again and checks the plan once
more. It never deletes or modifies an existing object, never touches a
pipeline named "Sales" (in any case or spacing, fullwidth, or with zero-width
characters), and never adds a stage to an existing pipeline (it tells you
which stage to add by hand instead).

Pipeline and stage names are matched exactly, because compile_ghl looks them
up exactly (`pipeline:<name>`, `stage:<pipeline>/<stage>`). A GHL name that
differs from the spec only by case, spacing or look-alike characters (NFKC
forms such as fullwidth letters, zero-width characters) is reported as a hand
fix, never created again as a near-duplicate.

A custom field is identified by its GHL key. A field the spec names by display
name (update_contact_field `field`, ai_step `output_field`) counts as existing
only when a GHL field's name matches it but for case and spacing, its name
gives the same key, or its fieldKey is that key. A GHL field that only looks
like it (see _norm) has another key, so it is another field: it is reported as
a hand fix, never counted as existing and never created again beside it. A
field the spec names by key ({{contact.<key>}}, `contact.<key>`, or a key
such as `call_time` in `field` / `output_field`) is decided by GHL's real key
alone (the fieldKey, or the key the GHL name gives): a GHL field that only
looks like it has another key, so the spec's field is created beside it.

Every run refreshes upwork_gen/catalog/ghl_ids_<location>.json (merge only,
no key is ever dropped, written atomically) so compile_ghl can resolve names
to ids.

If/Else tags come from compile_ghl.condition_tags, so both read a condition
the same way. A condition whose tags it cannot pin down derives no tags and
prints a warning naming the node (compile_ghl marks the same condition
unresolved); nothing is created for it.

Credentials: GHL_PIT_TOKEN (Private Integration token) and GHL_LOCATION_ID,
from the environment or from the repo's .env file (a one-line warning, never
the token, when group or others have any permission on that file).

Least privilege, whatever scopes the token carries: every request goes
through GHLClient.request, which sends only the eight calls in
allowed_requests (GET/POST on the configured location's tags, contact custom
fields and custom values, GET its pipelines, POST a pipeline for it) to
https://services.leadconnectorhq.com, and refuses anything else before any
network I/O (check_request). A redirect is never followed (the token would go
with it): any 3xx is an error, and on a create it counts as possibly created.

Exit codes: 0 everything exists; 1 objects still to create (dry run, or still
missing after --apply), an API or network error (including a read whose answer
is not the expected JSON list of objects with a string `name`), an id-map write
failure (the file on disk could not be replaced; the previous one is kept), or
an --apply that stopped part-way. "Stopped part-way" covers any failure after
at least one create succeeded: a later create (whatever the error), the
re-read of the account, the re-plan, the id-map write, or Ctrl-C. Every such
failure first prints the objects this run created. A create that got no
answer from GHL (Ctrl-C, a network error, anything but an HTTP error status)
or a 5xx answer (a gateway error can arrive after GHL saved the object) is
named as possibly created, since GHL may hold it; so is a create answered
with a redirect (3xx), which is never followed. Only an HTTP error status
below 500 (a 4xx), or a create the allowlist refused before sending it, is
taken as nothing created.
2 configuration / usage / spec problem / "Sales" guard, found before any
write: this includes `nodes` that is not a list, any param an object would be
named after that is not a name (a dict, a list, a bool, a number): a
pipeline, stage or `stages` entry, a tag step's, goal's or If/Else's `tag`,
update_contact_field's `field` or ai_step's `output_field`
(compile_ghl.name_param_problem, which compile_ghl shares), a name the spec
asks for (tag, custom field name or key, custom value key, pipeline, stage)
with a character outside plain printable ASCII (GHL names in a spec must be
plain ASCII, see check_ascii; names already in GHL may be anything), two
field names GHL would give one key, two field names that only look alike (GHL
would give them two keys, so two fields), a GHL_PIT_TOKEN with whitespace, a
control character or any other character outside printable ASCII inside it
(never printed), a GHL pipeline whose `stages` is not a list of named stages,
an empty --location, a location id that is not 10 to 40 letters and digits
(never printed), and a BASE_URL that is not
https://services.leadconnectorhq.com; 3 a hand fix in GHL: an existing
pipeline is missing a stage, a GHL pipeline or stage name differs from the
spec only by case, spacing or look-alike characters, or a GHL field only looks
like a field the spec names by display name (it has another key).
"""

import argparse
import http.client
import json
import os
import re
import stat
import sys
import tempfile
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import OrderedDict
from typing import Any, Callable, Dict, List, Optional, Tuple

from .compile_ghl import PIPELINE_OPS, condition_tags, name_param_problem

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATALOG_DIR = os.path.join(ROOT, "upwork_gen", "catalog")
ENV_PATH = os.path.join(ROOT, ".env")
BASE_URL = "https://services.leadconnectorhq.com"
# The only host the token is ever sent to, over HTTPS only (check_base_url).
API_HOST = "services.leadconnectorhq.com"
DEFAULT_LOCATION = "ebyNANPagaK7ycf1pfge"
# A GHL location id: letters and digits only (check_location).
_LOCATION_RE = re.compile(r"[A-Za-z0-9]{10,40}")
PROTECTED_PIPELINES = ("sales",)

# GHL's built-in contact merge fields ({{contact.<key>}}); never created.
STANDARD_CONTACT_FIELDS = {
    "id", "first_name", "last_name", "name", "full_name", "email", "phone", "phone_raw",
    "company_name", "address1", "full_address", "city", "state", "postal_code", "country",
    "website", "timezone", "date_of_birth", "source", "tags",
}
LARGE_TEXT_HINTS = ("notes", "description", "message")
PLACEHOLDER_VALUE = "PASTE-YOUR-VALUE"

# GHL builds a field's / custom value's key from its name (lowercased, one
# underscore per word break). This module creates the object named
# display_name(key), so only a key with _snake(display_name(key)) == key can
# ever come back as the same key: lowercase words joined by single
# underscores, none leading or trailing.
_KEY_RE = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
# Looks like a key rather than a display name (`call__time`, not `Call Notes`),
# so a bad one is reported instead of being created as a name.
_KEYISH_RE = re.compile(r"^[a-z0-9_]+$")
# Capture anything up to the braces so a bad key (callTime, call-time) is
# reported instead of silently skipped.
_CONTACT_RE = re.compile(r"\{\{\s*contact\.([^\s{}]+)\s*\}\}")
_CUSTOM_VALUE_RE = re.compile(r"\{\{\s*custom_values\.([^\s{}]+)\s*\}\}")
# A character outside plain printable ASCII (0x20-0x7E); see check_ascii.
_NOT_PLAIN = re.compile(r"[^\x20-\x7e]")

TAG_OPS = ("contact_tag_added", "contact_tag_removed", "add_tag", "remove_tag")
HAND_FIX = ("missing-stage", "name-mismatch")


class ConfigError(Exception):
    """Exit 2: something the author must fix before anything runs."""


class GHLError(Exception):
    """An API call failed (HTTP error or network error)."""


class GHLStatusError(GHLError):
    """GHL answered an API call with an HTTP error status, kept as `status`.
    On a create, a status below 500 (a 4xx) is GHL refusing it; a 5xx may
    come from a gateway after GHL saved the object, so GHL may hold it, as
    after any failure that is not GHL's answer."""

    def __init__(self, message: str, status: int) -> None:
        GHLError.__init__(self, message)
        self.status = status


class RequestRefused(GHLError):
    """A request outside the allowlist (check_request), refused before any
    network I/O: nothing was sent, so on a create GHL cannot hold it."""


class GHLRedirectError(GHLError):
    """GHL answered with a redirect (3xx), kept as `status`. It is never
    followed, since the token would go with it. The request did reach GHL,
    so on a create GHL may hold the object (in flight), as after any failure
    that is not a 4xx."""

    def __init__(self, message: str, status: int) -> None:
        GHLError.__init__(self, message)
        self.status = status


class ApplyError(Exception):
    """--apply stopped part-way; `created` lists what was made before it.
    `cause` may be a KeyboardInterrupt (Ctrl-C). `in_flight` is the create
    GHL may hold although it never confirmed it (no answer from GHL, or a 5xx
    answer: anything but a GHLStatusError below 500), or None."""

    def __init__(self, created: List[Tuple[str, str]], cause: BaseException,
                 in_flight: Optional[Tuple[str, str]] = None) -> None:
        Exception.__init__(self, str(cause))
        self.created = created
        self.cause = cause
        self.in_flight = in_flight


class IdMapWriteError(Exception):
    """Exit 1: the id map could not be written (the old file is kept)."""


# Invisible code points NFKC keeps that are not format (Cf) characters: the
# rest of Unicode's default-ignorable set (combining grapheme joiner, Hangul
# fillers, Khmer inherent vowels, Mongolian and other variation selectors).
_INVISIBLE = re.compile(r"[\u034f\u115f\u1160\u17b4\u17b5\u180b-\u180f\u3164\ufe00-\ufe0f\uffa0"
                        r"\U000e0000-\U000e0fff]")


def _norm(name: str) -> str:
    """Case-, spacing- and look-alike-insensitive form, only for spotting
    near-duplicates and for the "Sales" guard: NFKC (fullwidth SALES, U+FF33
    U+FF21 ..., is `SALES`; a no-break space is a space), then zero-width and
    other invisible characters dropped (`Sales` + U+200B is `Sales`). Never
    used for the exact names compile_ghl looks up."""
    text = unicodedata.normalize("NFKC", str(name))
    text = _INVISIBLE.sub("", "".join(c for c in text if unicodedata.category(c) != "Cf"))
    return " ".join(text.split()).casefold()


def _fold(name: str) -> str:
    """Case- and spacing-insensitive form of a custom field name, the only
    name rule besides the key that makes two field names one field. Two names
    with one _fold always get one _snake key. lower(), not casefold():
    casefold turns sharp s (U+00DF), long s (U+017F) and ligatures such as
    U+FB01 into ASCII letters, which gives another key."""
    return " ".join(str(name).split()).lower()


def _snake(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _key_round_trips(key: str) -> bool:
    """True when the object created for `key` gets `key` back from GHL."""
    return bool(_KEY_RE.match(key)) and _snake(display_name(key)) == key


def _suggest_key(key: str) -> str:
    """callTime -> call_time, call-time -> call_time."""
    return _snake(re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", key)) or "your_key"


# -- derivation -------------------------------------------------------------
class Needs(object):
    def __init__(self) -> None:
        self.tags = []  # type: List[str]
        # exact spec pipeline name -> ordered stage names
        self.pipelines = OrderedDict()  # type: Dict[str, List[str]]
        self.fields = []  # type: List[str]        # keys: {{contact.<key>}}
        self.field_names = []  # type: List[str]   # display names from `field` / `output_field`
        self.custom_values = []  # type: List[str]
        self.bad_keys = []  # type: List[Tuple[str, str, str]]  # (kind, key, where)
        self.warnings = []  # type: List[str]  # printed by run(); nothing is created for them
        # (kind, name, where) of every spec name that is not plain printable
        # ASCII, noted as it is collected, before any dedupe or drop could
        # hide it; check_ascii refuses them.
        self.not_ascii = []  # type: List[Tuple[str, str, str]]

    def _bad(self, kind: str, key: str, where: str) -> None:
        if (kind, key) not in [(k, v) for k, v, _w in self.bad_keys]:
            self.bad_keys.append((kind, key, where))

    def note_name(self, kind: str, name: str, where: str) -> None:
        """Note `name` for check_ascii if it is a name (not blank) with a
        character outside plain printable ASCII."""
        if name.strip() and _NOT_PLAIN.search(name) and \
                (kind, name) not in [(k, n) for k, n, _w in self.not_ascii]:
            self.not_ascii.append((kind, name, where))

    def add_tag(self, tag: str, where: str = "") -> None:
        # derive refuses a non-string `tag` first (name_param_problem); this
        # keeps any other caller from creating a tag named after a repr.
        if not isinstance(tag, str):
            raise ConfigError("tag {!r} is not a tag name (a string)".format(tag))
        tag = tag.strip()
        self.note_name("tag", tag, where)
        if tag and tag.lower() not in [t.lower() for t in self.tags]:
            self.tags.append(tag)

    def add_field_key(self, key: str, where: str) -> None:
        if key in STANDARD_CONTACT_FIELDS:
            return
        self.note_name("field key", key, where)
        if not _key_round_trips(key):
            self._bad("field", key, where)
        elif key not in self.fields:
            self.fields.append(key)

    def add_field_ref(self, value: Any, where: str) -> None:
        """A field named by update_contact_field.field / output_field: a key
        (`call_time`, `contact.call_time`, `{{contact.call_time}}`) or a
        display name (`Call Notes`). Anything but a string is a ConfigError,
        never a field named after its repr (derive refuses it first, through
        name_param_problem)."""
        if not isinstance(value, str):
            raise ConfigError("{}: must be a custom field name (a string), got {!r}".format(where, value))
        v = value.strip()
        if v.startswith("{{") and v.endswith("}}"):
            v = v[2:-2].strip()
        if not v:
            return
        if v.startswith("contact."):
            self.add_field_key(v[len("contact."):], where)
        elif _KEYISH_RE.match(v):
            self.add_field_key(v, where)
        else:
            # Noted before the standard-field and case/spacing tests below,
            # which a name that is not plain ASCII could get past.
            self.note_name("field", v, where)
            if _snake(v) not in STANDARD_CONTACT_FIELDS and \
                    _fold(v) not in [_fold(n) for n in self.field_names]:
                # Only a case/spacing respelling is dropped as the same field;
                # look-alikes are kept, and check_spec_names refuses them.
                self.field_names.append(v)

    def add_custom_value(self, key: str, where: str) -> None:
        self.note_name("custom value key", key, where)
        if not _key_round_trips(key):
            self._bad("custom_value", key, where)
        elif key not in self.custom_values:
            self.custom_values.append(key)


def _node_op(node: Dict[str, Any]) -> str:
    kind = node.get("kind", "")
    if kind == "flow.branch":
        return "if_else"
    if kind == "flow.wait":
        return "wait"
    if kind == "flow.noop":
        return "end"
    if kind in ("ai.llm", "ai.agent"):
        return "ai_step"
    return str(node.get("op") or "")


def _strings(value: Any) -> List[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        out = []  # type: List[str]
        for v in value.values():
            out.extend(_strings(v))
        return out
    if isinstance(value, (list, tuple)):
        out = []
        for v in value:
            out.extend(_strings(v))
        return out
    return []


def _node_tags(value: Any, where: str) -> List[str]:
    """params.tag of a tag step, trigger or goal: one tag name or a list of them."""
    if value is None or value == "":
        return []
    items = value if isinstance(value, list) else [value]
    for item in items:
        if not isinstance(item, str):
            raise ConfigError("{}: `tag` must be a tag name or a list of tag names, got {!r}".format(
                where, item))
    return items


def _add_unique(items: List[str], value: str) -> None:
    if value.strip() and value not in items:
        items.append(value)


def derive(spec: Dict[str, Any]) -> Needs:
    """Everything the spec needs to exist in the sub-account, in spec order.

    Stage order per pipeline: the node `stages` lists first (they set the
    order), then any other stage the spec names, appended if not listed."""
    needs = Needs()
    listed = OrderedDict()  # type: Dict[str, List[str]]
    loose = OrderedDict()  # type: Dict[str, List[str]]
    nodes = spec.get("nodes", [])
    if not isinstance(nodes, list):
        raise ConfigError("the spec's `nodes` must be a list of steps, got {!r}".format(nodes))
    for node in nodes:
        if not isinstance(node, dict):
            continue
        op = _node_op(node)
        p = node.get("params") or {}
        where = "node {!r}".format(node.get("key", "?"))
        if not isinstance(p, dict):
            raise ConfigError("{}: `params` must be an object, got {!r}".format(where, p))
        # Any param this module names an object after (pipeline, stage,
        # stages, tag, field, output_field) that is not a name would be
        # created under its repr; compile_ghl and the builder prompt refuse
        # the same specs.
        problem = name_param_problem(op, p)
        if problem:
            raise ConfigError("{}: {}".format(where, problem))
        if op in TAG_OPS or (op == "goal" and p.get("tag")):
            for tag in _node_tags(p.get("tag"), where):
                needs.add_tag(tag, where)
        if op == "if_else":
            tags = condition_tags(p, p.get("condition", ""))
            if tags is None:
                # compile_ghl reports this condition as one to set by hand.
                needs.warnings.append(
                    "{}: could not tell for certain which tags the If/Else condition {!r} tests, so no "
                    "tags were derived from it. If it tests tags, create them in GHL by hand or give the "
                    "node `params.tag`.".format(where, p.get("condition", "")))
            for tag in tags or []:
                needs.add_tag(tag, where)
        if op in PIPELINE_OPS and (p.get("pipeline") or "").strip():
            # name_param_problem has checked pipeline, stage and every entry
            # of `stages` are strings.
            name = p["pipeline"]
            needs.note_name("pipeline", name, where)
            listed.setdefault(name, [])
            loose.setdefault(name, [])
            for stage in p.get("stages") or []:
                _add_unique(listed[name], stage)
                needs.note_name("stage", stage, where)
            if p.get("stage") is not None:
                _add_unique(loose[name], p["stage"])
                needs.note_name("stage", p["stage"], where)
        if op == "update_contact_field" and p.get("field"):
            needs.add_field_ref(p["field"], where + " field")
        if op == "ai_step" and p.get("output_field"):
            needs.add_field_ref(p["output_field"], where + " output_field")
        for text in _strings(p):
            for key in _CONTACT_RE.findall(text):
                needs.add_field_key(key, "{} {{{{contact.{}}}}}".format(where, key))
            for key in _CUSTOM_VALUE_RE.findall(text):
                needs.add_custom_value(key, "{} {{{{custom_values.{}}}}}".format(where, key))
    for name, stages in listed.items():
        needs.pipelines[name] = stages + [s for s in loose[name] if s not in stages]
    # A display name that snakes to a key already needed is the same field.
    needs.field_names = [n for n in needs.field_names if _snake(n) not in needs.fields]
    return needs


def display_name(key: str) -> str:
    """call_time -> "Call Time"."""
    return " ".join(w[:1].upper() + w[1:] for w in key.split("_") if w)


def field_data_type(key: str) -> str:
    return "LARGE_TEXT" if any(h in key.lower() for h in LARGE_TEXT_HINTS) else "TEXT"


def check_protected(needs: Needs) -> None:
    # _norm, so no case, spacing, fullwidth or zero-width spelling of "Sales"
    # gets past it.
    for name in needs.pipelines:
        if _norm(name) in PROTECTED_PIPELINES:
            raise ConfigError(
                "spec references the pipeline {!r}, which is Lorenzo's real sales pipeline. "
                "Use a demo pipeline name in the spec (e.g. \"Call Booked Pipeline\").".format(name))


def check_keys(needs: Needs) -> None:
    lines = []
    for kind, key, where in needs.bad_keys:
        if kind == "field":
            lines.append(
                "field key {!r} ({}) must be lowercase words (letters, digits) joined by single "
                "underscores, with no leading or trailing underscore: GHL lowercases a field's name "
                "into its key, so {{{{contact.{}}}}} would never match a field. Use "
                "{{{{contact.{}}}}}.".format(key, where, key, _suggest_key(key)))
        else:
            lines.append(
                "custom value key {!r} ({}) must be lowercase words (letters, digits) joined by "
                "single underscores, with no leading or trailing underscore: GHL lowercases a custom "
                "value's name into its key, so {{{{custom_values.{}}}}} would never match. Use "
                "{{{{custom_values.{}}}}}.".format(key, where, key, _suggest_key(key)))
    if lines:
        raise ConfigError("\n".join(lines))


def _escaped(text: str) -> str:
    """`text` with every character outside plain printable ASCII escaped."""
    return "".join(c if " " <= c <= "~" else ascii(c)[1:-1] for c in text)


def check_ascii(needs: Needs) -> None:
    """Every name the spec asks for (tag, custom field name or key, custom
    value key, pipeline, stage) must be plain printable ASCII. This tool
    cannot tell which key GHL gives any other character, or which names GHL
    treats as one: a field named "Score" + U+00B2 was created beside the
    field "Score2" or {{contact.score2}} it looks like, because no look-alike
    check compares display names with keys. validate() runs this right after
    the "Sales" guard (which sees through look-alikes itself), before the
    checks such a name could get past. Names already in GHL are not
    restricted."""
    lines = []
    for kind, name, where in needs.not_ascii:
        lines.append("{} {}{}: GHL names in a spec must be plain ASCII (letters, digits, spaces and "
                     "ordinary punctuation), because which key GHL gives any other character, or "
                     "which names it treats as one, cannot be predicted, so the object could be "
                     "created twice or never match. Respell it in plain ASCII.".format(
                         kind, ascii(name), " ({})".format(_escaped(where)) if where else ""))
    if lines:
        raise ConfigError("\n".join(lines))


def check_spec_names(needs: Needs) -> None:
    """Spec names that differ only by case, spacing or look-alike characters
    would be looked up twice by compile_ghl and can never both match GHL."""
    def clashes(names: List[str]) -> List[List[str]]:
        groups = OrderedDict()  # type: Dict[str, List[str]]
        for n in names:
            groups.setdefault(_norm(n), []).append(n)
        return [g for g in groups.values() if len(g) > 1]

    for group in clashes(list(needs.pipelines)):
        raise ConfigError("the spec spells one pipeline {}: use one exact spelling everywhere".format(
            " and ".join(repr(n) for n in group)))
    for name, stages in needs.pipelines.items():
        for group in clashes(stages):
            raise ConfigError("the spec spells one stage of pipeline {!r} {}: use one exact spelling "
                              "everywhere".format(name, " and ".join(repr(s) for s in group)))
    # GHL turns a field's name into its key, so two names with one key would
    # be two creates of what GHL treats as one field.
    by_key = OrderedDict()  # type: Dict[str, List[str]]
    for n in needs.field_names:
        by_key.setdefault(_snake(n), []).append(n)
    for key, group in by_key.items():
        if len(group) > 1:
            raise ConfigError("the spec names one field {}: GHL gives both the key {!r}, so they "
                              "cannot be two fields. Use one exact spelling everywhere.".format(
                                  " and ".join(repr(n) for n in group), key))
    # Names that only look alike get different keys (checked just above), so
    # GHL would make two fields of what reads as one.
    for group in clashes(needs.field_names):
        raise ConfigError("the spec spells one field {}: they differ only by case, spacing or "
                          "look-alike characters, but GHL gives them different keys, so they would "
                          "be two fields. Use one exact spelling everywhere.".format(
                              " and ".join(repr(n) for n in group)))


def validate(needs: Needs) -> None:
    """Everything that must hold before the account is read or written."""
    check_protected(needs)
    check_ascii(needs)
    check_keys(needs)
    check_spec_names(needs)


# -- config -----------------------------------------------------------------
def read_env_file(path: str) -> Dict[str, str]:
    out = {}  # type: Dict[str, str]
    if not os.path.exists(path):
        return out
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[len("export "):]
            k, v = line.split("=", 1)
            v = v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                v = v[1:-1]
            out[k.strip()] = v
    return out


def check_base_url(base_url: Optional[str] = None) -> None:
    """BASE_URL must be exactly https://services.leadconnectorhq.com: HTTPS,
    GHL's API host, no port, user, path, query or fragment."""
    base = BASE_URL if base_url is None else base_url
    if base != "https://" + API_HOST:
        # The value is not printed: it could hold a user or password.
        raise ConfigError("BASE_URL must be https://{} exactly (HTTPS to GHL's API host, no port, "
                          "user, path or anything else); nothing was sent".format(API_HOST))


def check_location(location: Any) -> None:
    """A GHL location id is 10 to 40 letters and digits. The value is never
    printed: a token pasted into the wrong variable would leak."""
    if not isinstance(location, str) or not _LOCATION_RE.fullmatch(location):
        raise ConfigError("the GHL location id (--location, GHL_LOCATION_ID) is not a location id: it "
                          "must be 10 to 40 letters and digits, nothing else. Nothing was sent (the "
                          "value is not printed).")


def warn_loose_env_file(env_path: str, warn: Callable[[str], None]) -> None:
    """One line when the .env file has any group or other permission bit
    (read, write or execute). Warns only; never prints the file's contents."""
    try:
        mode = stat.S_IMODE(os.stat(env_path).st_mode)
    except OSError:
        return
    if mode & 0o077:
        warn("warning: {} can be accessed by other users (permissions {:o}); run: chmod 600 {}".format(
            env_path, mode, env_path))


def load_credentials(location: Optional[str] = None, env_path: str = ENV_PATH,
                     environ: Optional[Dict[str, str]] = None,
                     warn: Optional[Callable[[str], None]] = None) -> Tuple[str, str]:
    environ = os.environ if environ is None else environ
    if os.path.exists(env_path):
        warn_loose_env_file(env_path, warn or (lambda msg: sys.stderr.write(msg + "\n")))
    file_env = read_env_file(env_path)
    token = environ.get("GHL_PIT_TOKEN") or file_env.get("GHL_PIT_TOKEN") or ""
    if not token.strip():
        raise ConfigError("GHL_PIT_TOKEN is not set: add GHL_PIT_TOKEN=<your GHL Private "
                          "Integration token> to {}".format(env_path))
    # Refused here, never echoed: sent as a header, a line break would make the
    # HTTP library quote the whole value in its error message.
    if any(c.isspace() or unicodedata.category(c) == "Cc" for c in token.strip()):
        raise ConfigError("GHL_PIT_TOKEN has whitespace or a control character inside it (a line "
                          "break, tab or space), so it is not a valid token: set GHL_PIT_TOKEN to the "
                          "token alone, on one line, in the environment or in {}".format(env_path))
    # Anything else outside printable ASCII (a zero-width space, a byte-order
    # mark, an accented letter) would fail in the HTTP library with an error
    # that gives the character's position, and so the token's length. Refused
    # here with a fixed message: no part of the token, its length or a position.
    if any(not "\x21" <= c <= "\x7e" for c in token.strip()):
        raise ConfigError("GHL_PIT_TOKEN has a character outside plain printable ASCII (such as an "
                          "invisible zero-width space or byte-order mark), so it is not a valid token: "
                          "set GHL_PIT_TOKEN to the token alone, as plain text, in the environment or "
                          "in {}".format(env_path))
    if location == "":
        raise ConfigError("--location is empty: pass the GHL location id (10 to 40 letters and "
                          "digits), or leave --location out to use GHL_LOCATION_ID. Nothing was sent.")
    loc = (location or environ.get("GHL_LOCATION_ID") or file_env.get("GHL_LOCATION_ID")
           or DEFAULT_LOCATION).strip()
    check_location(loc)
    return token.strip(), loc


# -- HTTP -------------------------------------------------------------------
Transport = Callable[[str, str, Dict[str, str], Optional[bytes]], Tuple[int, Any]]
DETAIL_LIMIT = 300
# Sent on every request: GHL's API sits behind Cloudflare, which refuses
# Python's default User-Agent ("Python-urllib/3.x") with a 403, error 1010.
USER_AGENT = "AdveroSolutions-ghl-prereqs/1.0"
# Cloudflare's own wording for that refusal ("error code: 1010" in its plain
# answer, "Error 1010" on its page, "error_code": 1010 in its JSON), so a
# trace id or any other text that merely holds "1010" is not taken for it.
_CLOUDFLARE_1010 = re.compile(r'(?:(?<!\w)error code: 1010|(?<!\w)error 1010|"error_code": ?1010)(?!\d)',
                              re.IGNORECASE)


def allowed_requests(location: str) -> frozenset:
    """Every (method, path and query) this module sends, and nothing else:
    exactly the call sites in GHLClient below. No read pages, so there are no
    pagination parameters."""
    loc = "/locations/" + location
    return frozenset([
        ("GET", "/opportunities/pipelines?locationId=" + location),   # GHLClient.pipelines
        ("GET", loc + "/tags"),                                       # GHLClient.tags
        ("GET", loc + "/customFields?model=contact"),                 # GHLClient.custom_fields
        ("GET", loc + "/customValues"),                               # GHLClient.custom_values
        ("POST", loc + "/tags"),                                      # GHLClient.create_tag
        ("POST", loc + "/customFields"),                              # GHLClient._create_field
        ("POST", loc + "/customValues"),                              # GHLClient.create_custom_value
        ("POST", "/opportunities/pipelines"),                         # GHLClient.create_pipeline
    ])


def check_request(method: str, url: str, location: str, body: Any = None,
                  redact: Callable[[str], str] = lambda text: text) -> None:
    """Refuse (RequestRefused) any request but the ones in allowed_requests,
    before any network I/O: another method (PUT, PATCH, DELETE...), another
    host or plain http, a path with `..`, `//`, a fragment, a percent-encoded
    character (an encoded slash) or anything outside plain printable ASCII,
    another location id (in the path, the query or a pipeline's body), a
    GET with a body, an address that cannot be parsed, or any other path or
    query. The token is never part of the message."""
    def refuse(reason: str) -> None:
        shown = _escaped(redact(url))
        if len(shown) > DETAIL_LIMIT:
            shown = shown[:DETAIL_LIMIT] + "..."
        raise RequestRefused("{} {} refused before sending: {}. This tool only makes the GHL calls it "
                             "needs; nothing was sent".format(_escaped(redact(str(method)))[:20], shown,
                                                              reason))

    if method not in ("GET", "POST"):
        refuse("method {} is never used by this tool (only GET and POST)".format(
            _escaped(redact(str(method)))[:20]))
    if not isinstance(location, str) or not _LOCATION_RE.fullmatch(location):
        refuse("the configured location id is not a location id")
    base = "https://" + API_HOST
    if not url.startswith("https://"):
        refuse("not HTTPS")
    host = url[len("https://"):].split("/", 1)[0]
    try:
        netloc = urllib.parse.urlsplit(url).netloc
    except ValueError:  # a lone [ or ], or a look-alike of / ? # @ : in the host
        netloc = None
    if host != API_HOST or netloc != API_HOST or not url.startswith(base + "/"):
        refuse("the host is not {}".format(API_HOST))
    path = url[len(base):]
    if _NOT_PLAIN.search(path) or " " in path:
        refuse("the path has a space, a control character or a character outside plain ASCII")
    if "#" in path:
        refuse("the path has a fragment (#)")
    if "%" in path:
        refuse("the path has a percent-encoded character (such as an encoded slash)")
    if "\\" in path:
        refuse("the path has a backslash")
    if ".." in path:
        refuse("the path has `..`")
    if "//" in path:
        refuse("the path has `//`")
    route, _sep, query = path.partition("?")
    segments = route.split("/")
    if len(segments) > 2 and segments[1] == "locations" and segments[2] != location:
        refuse("another location id than the configured one")
    try:
        pairs = urllib.parse.parse_qsl(query, keep_blank_values=True)
    except ValueError:
        refuse("the query cannot be parsed")
    if any(k == "locationId" and v != location for k, v in pairs):
        refuse("another location id than the configured one")
    if (method, path) not in allowed_requests(location):
        refuse("not an endpoint this tool uses")
    if method == "POST" and route == "/opportunities/pipelines" and \
            not (isinstance(body, dict) and body.get("locationId") == location):
        refuse("the pipeline is not for the configured location id")
    if method == "GET" and body is not None:
        # A body on a read could name another location id; no read sends one.
        refuse("a GET never carries a body")


class _RefuseRedirects(urllib.request.HTTPRedirectHandler):
    """Never follow a redirect: urllib would resend the request, the
    Authorization header included, to the new address (https to http too).
    Any 3xx raises GHLRedirectError and no request goes to the target."""

    def _refuse(self, req: Any, fp: Any, code: int, msg: str, headers: Any) -> Any:
        try:
            fp.close()
        except Exception:  # closing the answer is best effort
            pass
        raise GHLRedirectError("HTTP {}: a redirect, refused and not followed (the token is never "
                               "sent to another address)".format(code), int(code))

    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any,
                         newurl: str) -> Any:
        return self._refuse(req, fp, code, msg, headers)


for _code in range(300, 400):  # every 3xx, 308 included (Python 3.9 only knows 301-307)
    setattr(_RefuseRedirects, "http_error_{}".format(_code), _RefuseRedirects._refuse)
del _code


def urllib_transport(method: str, url: str, headers: Dict[str, str],
                     body: Optional[bytes]) -> Tuple[int, Any]:
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    opener = urllib.request.build_opener(_RefuseRedirects())
    try:
        with opener.open(req, timeout=30) as resp:
            status, raw = resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        if 300 <= exc.code < 400:
            try:
                exc.close()
            except Exception:  # closing the answer is best effort
                pass
            raise GHLRedirectError("HTTP {}: a redirect, refused and not followed (the token is "
                                   "never sent to another address)".format(exc.code), exc.code)
        status, raw = exc.code, exc.read()
    text = raw.decode("utf-8", "replace") if raw else ""
    try:
        return status, json.loads(text) if text else {}
    except ValueError:
        return status, text


class GHLClient(object):
    def __init__(self, token: str, location: str, transport: Optional[Transport] = None) -> None:
        check_location(location)
        self._token = token
        self.location = location
        self.transport = transport or urllib_transport

    def redact(self, text: str) -> str:
        return text.replace(self._token, "<GHL_PIT_TOKEN>") if self._token else text

    def _detail(self, payload: Any) -> str:
        detail = payload if isinstance(payload, str) else json.dumps(payload)
        # Redact the whole text first: truncating first could cut the token
        # in half and leak the part that no longer matches.
        detail = self.redact(detail)
        if len(detail) > DETAIL_LIMIT:
            detail = detail[:DETAIL_LIMIT] + "..."
        return detail

    def request(self, method: str, path: str, body: Optional[Dict[str, Any]] = None,
                version: str = "2021-07-28") -> Any:
        """The one place every request goes through: check_request refuses
        anything outside the allowlist before the transport is called, and a
        redirect (3xx) is never followed."""
        url = BASE_URL + path
        check_request(method, url, self.location, body, self.redact)
        headers = {"Authorization": "Bearer " + self._token, "Version": version,
                   "Accept": "application/json", "User-Agent": USER_AGENT}
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode("utf-8")
        where = "{} {}".format(method, path.split("?")[0])
        try:
            status, payload = self.transport(method, url, headers, data)
        except GHLRedirectError as exc:
            raise GHLRedirectError(self.redact("{} -> {}".format(where, exc)), exc.status)
        except (OSError, http.client.HTTPException) as exc:  # URLError, timeouts, resets
            raise GHLError(self.redact("{} -> network error: {}".format(where, exc)))
        if 300 <= int(status) < 400:
            raise GHLRedirectError(self.redact(
                "{} -> HTTP {}: a redirect, refused and not followed (the token is never sent to "
                "another address)".format(where, int(status))), int(status))
        if not 200 <= int(status) < 300:
            detail = self._detail(payload)
            text = payload if isinstance(payload, str) else json.dumps(payload)
            if int(status) == 403 and _CLOUDFLARE_1010.search(text):
                # Cloudflare in front of GHL refused the request (it judged
                # the client by its User-Agent); GHL never saw it.
                detail = "GHL's firewall refused the request (Cloudflare 1010, User-Agent): " + detail
            raise GHLStatusError(self.redact("{} -> HTTP {}: {}".format(where, status, detail)),
                                 int(status))
        return payload

    def read_list(self, path: str, key: str) -> List[Dict[str, Any]]:
        """GET a list. Fails closed: a 2xx answer that is not a JSON object
        holding `key` as a list of objects (an HTML page, `{}`, an error body),
        or an object in it without a string `name`, raises GHLError, so a bad
        read is never taken as "nothing exists"."""
        payload = self.request("GET", path)
        items = payload.get(key) if isinstance(payload, dict) else None
        if not isinstance(items, list) or not all(isinstance(i, dict) for i in items):
            raise GHLError(self.redact("GET {} -> the answer is not a JSON object with a `{}` list, "
                                       "so the account cannot be read safely: {}".format(
                                           path.split("?")[0], key, self._detail(payload))))
        for item in items:
            if not isinstance(item.get("name"), str):
                raise GHLError(self.redact("GET {} -> an object in `{}` has no string `name`, so the "
                                           "account cannot be read safely: {}".format(
                                               path.split("?")[0], key, self._detail(item))))
        return items

    # reads
    def pipelines(self) -> List[Dict[str, Any]]:
        """Every pipeline, each with `stages` absent/null or a list of objects
        with a string `name`; any other shape is a ConfigError (nothing has
        been written when it is raised), never a traceback."""
        items = self.read_list("/opportunities/pipelines?locationId=" + self.location, "pipelines")
        for p in items:
            stages = p.get("stages")
            if stages is not None and (not isinstance(stages, list) or not all(
                    isinstance(s, dict) and isinstance(s.get("name"), str) for s in stages)):
                raise ConfigError(self.redact(
                    "GHL pipeline {!r} has a `stages` value that is not a list of named stages, so "
                    "the account cannot be compared with the spec safely: {}".format(
                        p["name"], self._detail(stages))))
        return items

    def tags(self) -> List[Dict[str, Any]]:
        return self.read_list("/locations/{}/tags".format(self.location), "tags")

    def custom_fields(self) -> List[Dict[str, Any]]:
        return self.read_list("/locations/{}/customFields?model=contact".format(self.location),
                              "customFields")

    def custom_values(self) -> List[Dict[str, Any]]:
        return self.read_list("/locations/{}/customValues".format(self.location), "customValues")

    # creates (the only writes this module makes)
    def create_tag(self, name: str) -> Any:
        return self.request("POST", "/locations/{}/tags".format(self.location), {"name": name})

    def _create_field(self, name: str, data_type: str) -> Any:
        return self.request("POST", "/locations/{}/customFields".format(self.location), {
            "name": name, "dataType": data_type, "model": "contact"})

    def create_field(self, key: str) -> Any:
        return self._create_field(display_name(key), field_data_type(key))

    def create_field_named(self, name: str) -> Any:
        return self._create_field(name, field_data_type(_snake(name)))

    def create_custom_value(self, key: str) -> Any:
        return self.request("POST", "/locations/{}/customValues".format(self.location), {
            "name": display_name(key), "value": PLACEHOLDER_VALUE})

    def create_pipeline(self, name: str, stages: List[str]) -> Any:
        if _norm(name) in PROTECTED_PIPELINES:
            raise ConfigError("refusing to create a pipeline named {!r}".format(name))
        if not stages:
            raise ConfigError("refusing to create pipeline {!r} with no stages".format(name))
        return self.request("POST", "/opportunities/pipelines", {
            "name": name, "locationId": self.location,
            "stages": [{"name": s, "position": i} for i, s in enumerate(stages)]},
            version="v3")


# -- state and plan -----------------------------------------------------------
class State(object):
    def __init__(self, pipelines: List[Dict[str, Any]], tags: List[Dict[str, Any]],
                 fields: List[Dict[str, Any]], values: List[Dict[str, Any]]) -> None:
        self.pipelines = pipelines
        self.tags = tags
        self.fields = fields
        self.values = values

    @staticmethod
    def fetch(client: GHLClient) -> "State":
        return State(client.pipelines(), client.tags(), client.custom_fields(), client.custom_values())

    def find_pipeline(self, name: str) -> Optional[Dict[str, Any]]:
        """Exact name, as compile_ghl's `pipeline:<name>` lookup needs."""
        for p in self.pipelines:
            if str(p.get("name", "")) == name:
                return p
        return None

    def near_pipelines(self, name: str) -> List[str]:
        """GHL pipeline names that differ from `name` only by case, spacing or
        look-alike characters (see _norm)."""
        return [str(p.get("name", "")) for p in self.pipelines
                if str(p.get("name", "")) != name and _norm(p.get("name", "")) == _norm(name)]

    def find_tag(self, name: str) -> Optional[Dict[str, Any]]:
        for t in self.tags:
            if str(t.get("name", "")).strip().lower() == name.strip().lower():
                return t
        return None

    def find_field(self, key: str) -> Optional[Dict[str, Any]]:
        for f in self.fields:
            fk = str(f.get("fieldKey", ""))
            if fk in ("contact." + key, key) or _snake(str(f.get("name", ""))) == key:
                return f
        return None

    def find_field_named(self, name: str) -> Optional[Dict[str, Any]]:
        """The same field: its name matches but for case and spacing, its name
        gives the same key, or its fieldKey is that key. Never a look-alike
        (see near_fields): GHL gives that one another key."""
        for f in self.fields:
            have = str(f.get("name", ""))
            if _fold(have) == _fold(name) or _snake(have) == _snake(name) \
                    or str(f.get("fieldKey", "")) == "contact." + _snake(name):
                return f
        return None

    def near_fields(self, name: str) -> List[str]:
        """GHL field names that match `name` only as look-alikes (_norm), for
        a name find_field_named found no field for."""
        return [str(f.get("name", "")) for f in self.fields if _norm(f.get("name", "")) == _norm(name)]

    def find_value(self, key: str) -> Optional[Dict[str, Any]]:
        for v in self.values:
            fk = re.sub(r"[{}\s]", "", str(v.get("fieldKey", "")))
            if fk == "custom_values." + key or _snake(str(v.get("name", ""))) == key:
                return v
        return None


# Plan row: (kind, name, status, detail)
Row = Tuple[str, str, str, str]


def plan(needs: Needs, state: State) -> List[Row]:
    rows = []  # type: List[Row]
    for tag in needs.tags:
        rows.append(("tag", tag, "exists" if state.find_tag(tag) else "create", ""))
    for name, stages in needs.pipelines.items():
        existing = state.find_pipeline(name)
        if not existing:
            near = state.near_pipelines(name)
            if near:
                rows.append(("pipeline", name, "name-mismatch",
                             "GHL has pipeline {!r}, which differs from the spec's {!r} only by case, "
                             "spacing or look-alike characters: rename it in GHL or change the spec so "
                             "the names match exactly".format(near[0], name)))
                continue
            if not stages:
                raise ConfigError(
                    "pipeline {!r} needs at least one stage and the spec names none: give its "
                    "opportunity step a `stage` (or a `stages` list)".format(name))
            rows.append(("pipeline", name, "create", "stages: " + ", ".join(stages)))
            continue
        rows.append(("pipeline", name, "exists", ""))
        have = [str(s.get("name", "")) for s in existing.get("stages") or []]
        for stage in stages:
            label = "{}/{}".format(name, stage)
            if stage in have:
                rows.append(("stage", label, "exists", ""))
                continue
            near = [h for h in have if _norm(h) == _norm(stage)]
            if near:
                detail = ("pipeline {!r} has stage {!r}, which differs from the spec's {!r} only by "
                          "case, spacing or look-alike characters: rename it in GHL or change the "
                          "spec so the names match exactly".format(name, near[0], stage))
            else:
                detail = "add stage {!r} to pipeline {!r} by hand in GHL".format(stage, name)
            rows.append(("stage", label, "missing-stage", detail))
    for key in needs.fields:
        rows.append(("field", key, "exists" if state.find_field(key) else "create",
                     "{} ({})".format(display_name(key), field_data_type(key))))
    for name in needs.field_names:
        found = state.find_field_named(name)
        near = [] if found else state.near_fields(name)
        if near:
            rows.append(("field", name, "name-mismatch",
                         "GHL has field {!r}, which differs from the spec's {!r} only by case, "
                         "spacing or look-alike characters (GHL gives it another key): rename it in "
                         "GHL or change the spec so the names match exactly".format(near[0], name)))
            continue
        rows.append(("field", name, "exists" if found else "create",
                     "{} ({})".format(name, field_data_type(_snake(name)))))
    for key in needs.custom_values:
        rows.append(("custom_value", key, "exists" if state.find_value(key) else "create",
                     display_name(key)))
    return rows


def apply_plan(client: GHLClient, needs: Needs, rows: List[Row],
               created: Optional[List[Tuple[str, str]]] = None) -> List[Row]:
    """Create every "create" row. Each create that succeeds is appended to
    `created` at once (run() passes its own list, so it knows what GHL holds
    wherever the run stops). Raises ApplyError (with what was already
    created) if a create fails or is interrupted (Ctrl-C) part-way; unless
    GHL answered it with an HTTP error status below 500 (a 4xx) or the
    allowlist refused it before sending (RequestRefused), the create is
    `in_flight`: a 5xx may come from a gateway after GHL saved it, and a
    redirect (3xx, never followed) reached GHL too."""
    out = []  # type: List[Row]
    created = [] if created is None else created
    for kind, name, status, detail in rows:
        if status == "create":
            try:
                if kind == "tag":
                    client.create_tag(name)
                elif kind == "pipeline":
                    client.create_pipeline(name, needs.pipelines[name])
                elif kind == "field" and name in needs.field_names:
                    client.create_field_named(name)
                elif kind == "field":
                    client.create_field(name)
                elif kind == "custom_value":
                    client.create_custom_value(name)
            except BaseException as exc:  # any failure, Ctrl-C too: say what already exists in GHL
                # Only an HTTP error status below 500 is GHL saying it made
                # nothing. A 5xx may come from a gateway after GHL saved the
                # object, and after Ctrl-C, a network error or anything else the
                # request may have reached GHL, so this object may exist now.
                # A request the allowlist refused was never sent.
                refused = isinstance(exc, RequestRefused) or \
                    (isinstance(exc, GHLStatusError) and exc.status < 500)
                in_flight = None if refused else (kind, name)
                raise ApplyError(list(created), exc, in_flight)
            created.append((kind, name))
            status = "created"
        out.append((kind, name, status, detail))
    return out


# -- id map -------------------------------------------------------------------
def id_entries(state: State) -> Dict[str, str]:
    out = {}  # type: Dict[str, str]
    for p in state.pipelines:
        if p.get("id") and p.get("name"):
            out["pipeline:" + p["name"]] = p["id"]
            for s in p.get("stages") or []:
                if s.get("id") and s.get("name"):
                    out["stage:{}/{}".format(p["name"], s["name"])] = s["id"]
    for t in state.tags:
        if t.get("id") and t.get("name"):
            out["tag:" + t["name"]] = t["id"]
    for f in state.fields:
        if f.get("id") and f.get("name"):
            out["field:" + f["name"]] = f["id"]
    for v in state.values:
        if v.get("id") and v.get("name"):
            out["custom_value:" + v["name"]] = v["id"]
    return out


def id_map_path(location: str, catalog_dir: str = CATALOG_DIR) -> str:
    return os.path.join(catalog_dir, "ghl_ids_{}.json".format(location))


def read_id_map(path: str) -> Dict[str, Any]:
    """The existing map, or {} when there is none. ConfigError (nothing is
    written) when it is not a JSON object."""
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as fh:
        try:
            current = json.load(fh)
        except ValueError as exc:
            raise ConfigError("{} is not valid JSON ({}); fix it by hand, nothing was written".format(
                path, exc))
    if not isinstance(current, dict):
        raise ConfigError("{} is not a JSON object (it holds a {}); fix it by hand, nothing was "
                          "written".format(path, type(current).__name__))
    return current


def write_json_atomic(path: str, data: Dict[str, Any]) -> None:
    """Write to a temp file beside `path`, fsync, then rename over it, so a
    failed write never leaves `path` half-written."""
    directory = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(prefix="." + os.path.basename(path) + ".", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, sort_keys=True, ensure_ascii=False)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        try:
            mode = stat.S_IMODE(os.stat(path).st_mode)
        except OSError:
            mode = 0o644
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    try:  # make the rename itself durable; best effort
        dfd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    except OSError:
        pass


def refresh_id_map(path: str, state: State) -> Dict[str, Any]:
    current = read_id_map(path)
    current.update(id_entries(state))
    try:
        write_json_atomic(path, current)
    except OSError as exc:
        raise IdMapWriteError("could not write the id map {}: {}; the previous file is "
                              "unchanged".format(path, exc))
    return current


# -- CLI --------------------------------------------------------------------
def render_table(rows: List[Row], applied: bool) -> str:
    label = {"exists": "exists", "created": "created",
             "create": "not created" if applied else "will create",
             "missing-stage": "MISSING STAGE", "name-mismatch": "NAME MISMATCH"}
    lines = [("KIND", "NAME", "STATUS", "DETAIL")]
    lines += [(k, n, label.get(s, s), d) for k, n, s, d in rows]
    widths = [max(len(r[i]) for r in lines) for i in range(3)]
    return "\n".join("  ".join([r[0].ljust(widths[0]), r[1].ljust(widths[1]),
                                r[2].ljust(widths[2]), r[3]]).rstrip() for r in lines)


def _describe(items: List[Tuple[str, str]]) -> str:
    return ", ".join("{} {!r}".format(k, n) for k, n in items)


def run(argv: Optional[List[str]] = None, transport: Optional[Transport] = None,
        environ: Optional[Dict[str, str]] = None, env_path: str = ENV_PATH,
        catalog_dir: str = CATALOG_DIR, out: Any = None) -> int:
    out = out or sys.stdout
    parser = argparse.ArgumentParser(prog="python3 -m upwork_gen.ghl_prereqs",
                                     description="Create the GHL objects a spec needs (dry run by default).")
    parser.add_argument("spec")
    parser.add_argument("--apply", action="store_true", help="create what is missing (never modifies or deletes)")
    parser.add_argument("--location", help="GHL location id (default GHL_LOCATION_ID or {})".format(DEFAULT_LOCATION))
    args = parser.parse_args(argv)

    def say(msg: str) -> None:
        out.write(msg + "\n")

    client = None  # type: Optional[GHLClient]

    def safe(msg: str) -> str:
        return client.redact(msg) if client else msg

    applied = False
    # Objects this run made, appended by apply_plan the moment each create
    # succeeds, so it is right wherever the run stops.
    created = []  # type: List[Tuple[str, str]]

    def stopped(done: List[Tuple[str, str]], cause: BaseException,
                in_flight: Optional[Tuple[str, str]] = None) -> int:
        """Exit 1 for an --apply that stopped part-way (an error or Ctrl-C):
        GHL now holds `done`, so it is listed before the error. GHL may hold
        `in_flight` too (a create that got no answer, or a 5xx), so it is
        named, and "nothing was created" is never said then."""
        if done:
            say("already created before the error: " + safe(_describe(done)))
        elif not in_flight:
            say("nothing was created before the error.")
        if in_flight:
            say("possibly created: " + safe(_describe([in_flight])) +
                " was in flight; GHL may hold it; a dry run shows which.")
        if isinstance(cause, KeyboardInterrupt):
            text = "interrupted (Ctrl-C)"
        elif isinstance(cause, (GHLError, ConfigError, IdMapWriteError)):
            text = str(cause)
        else:
            text = "{}: {}".format(type(cause).__name__, cause)
        say(("error after the creates: " if applied else "error: --apply stopped part-way: ") + safe(text))
        say("rerun to finish; only what is still missing is created.")
        return 1

    try:
        with open(args.spec, "r", encoding="utf-8") as fh:
            spec = json.load(fh)
        if not isinstance(spec, dict):
            raise ConfigError("{} is not a spec (expected a JSON object)".format(args.spec))
        needs = derive(spec)
        validate(needs)
        check_base_url()
        token, location = load_credentials(args.location, env_path, environ, warn=say)
        client = GHLClient(token, location, transport)
        path = id_map_path(location, catalog_dir)
        read_id_map(path)  # refuse a broken map before anything is written
        state = State.fetch(client)
        rows = plan(needs, state)
        final = rows
        if args.apply and any(r[2] == "create" for r in rows):
            rows = apply_plan(client, needs, rows, created)
            applied = True
        try:
            if applied:
                state = State.fetch(client)
                final = plan(needs, state)
            refresh_id_map(path, state)
        except BaseException as exc:  # Ctrl-C too
            if created:  # say what now exists in GHL, whatever failed after it
                raise ApplyError(list(created), exc)
            raise
    except ApplyError as exc:
        # A create failed or was interrupted part-way, or the re-read /
        # re-plan / id-map write after the creates failed: either way GHL now
        # holds these objects, so they are listed before the error.
        return stopped(exc.created, exc.cause, exc.in_flight)
    except (GHLError, IdMapWriteError) as exc:
        say("error: " + safe(str(exc)))
        return 1
    except (ConfigError, IOError, ValueError) as exc:
        say("error: " + safe(str(exc)))
        return 2
    except BaseException as exc:
        # Ctrl-C (or anything unforeseen) between two creates, outside the
        # wrappers above. Before any create nothing was written: propagate as
        # usual. After one, GHL holds objects: list them and exit 1.
        if not created:
            raise
        return stopped(list(created), exc)

    say("GHL prerequisites for {} (location {}, {})".format(
        spec.get("title", args.spec), location, "apply" if args.apply else "dry run"))
    say(render_table(rows, applied))
    say("id map refreshed: " + path)
    for warning in needs.warnings:
        say("warning: " + safe(warning))
    hand = [r for r in final if r[2] in HAND_FIX]
    pending = [r for r in final if r[2] == "create"]
    for r in hand:
        say("action needed: " + r[3] + ", then rerun.")
    if pending:
        if applied:
            say("{} object(s) still missing after --apply: {}. Rerun to retry.".format(
                len(pending), _describe([(r[0], r[1]) for r in pending])))
        else:
            say("{} object(s) to create. Rerun with --apply to create them.".format(len(pending)))
    if hand:
        return 3
    if pending:
        return 1
    if needs.warnings:
        say("everything else the spec needs exists; the tags of the condition(s) warned about above "
            "were not checked.")
    else:
        say("everything the spec needs exists.")
    return 0


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
