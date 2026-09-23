"""GoHighLevel workflow compiler.

Emits the JSON that the "GHL Workflow Backup & Audit" Chrome extension imports
into an open workflow (reference exports: reference/ghl_export_sales_request_follow_up.json,
captured 2026-09-21 from a workflow GHL's own builder produced, and
reference/ghl_export_reference_all_types.json, captured 2026-09-23 after
examples/ghl_reference_all_types.json was imported into a Draft). The shape:

- flat `nodes` list; each node has `type`, `id` (uuid4), `name`, `attributes`,
  `next` (id, "" at a chain end, or a list of branch ids on an if_else),
  `parentKey` (the node before it), `order` (position in its chain) and, inside a
  branch, `parent` (the branch node id). Names are mirrored as nextName /
  parentKeyName / parentName for a human reading the file only: the importer
  (lib/importer.js stripAnnotations) deletes those *Name keys before writing
  and keeps every id exactly as the file has it, so the ids must be right here.
- an if_else is a `condition-node` whose branches are child nodes of type if_else
  with nodeType `branch-yes` (else: `branch-no`, attributes {"else": true}).
- `triggers` is a separate list; `references` maps every id to its name.

Which shapes are verified: VERIFIED means the key set matches a real export
above in a shape GHL's builder saved ("export 2026-09-23": Lorenzo imported the
reference spec into a Draft, checked every step, re-added the broken ones by
hand, saved and exported); FIELD means it imported cleanly on 2026-09-22
(Cal.com spec, 12/12 steps); RESEARCH / UNVERIFIED means reverse-engineered and
not yet saved by GHL (reference/GHL_REFERENCE_CHECKLIST.md is how those get
locked). Keys the extension's exporter adds (every *Name / *_name mirror of an
id: pipelineName, valueName, targetNodeName, fieldName, user_listNames,
location_name, ...) are stripped again by its importer and are not part of any
shape. Keys GHL fills in with defaults are adopted only where the panel needs
them; each op says which. Per-location ids (users, fields, pipelines, stages,
workflows) come only from the id map, never from the export.

Things a human must check after import but that do not stop the compile (a Go
To into another If/Else branch, an Assign to user with no known user) are
GHLCompileWarning warnings, also kept on GHLCompiler.warnings.

GHL actions are a single line except at an if_else, so a non-branch step with
two successors is an error, not a silently dropped edge. Two branches that meet
again are compiled by copying the shared tail into each branch (fresh ids),
which is what a human does in the GHL builder. `end` emits nothing. A loop
edge (`"loop": true`) becomes a Go To step pointing back at its target, the
same record op go_to emits; a loop that cannot be a Go To is a SpecError.

A spec whose triggers start separate chains (no shared step) compiles to one
workflow per trigger: compile_ghl_many. Triggers that share steps stay in one
workflow (GHL allows several triggers per workflow).

Spec vocabulary is the GHL one from compile_ghl_prompt (app "ghl" + op + params).
Pipeline/stage/form/workflow ids come from `ids` (name -> id), fetched from the
account through the GHL API; unknown names are emitted with a placeholder id and
reported so a human sets them after import (the importer does not look ids up
by name). If/Else conditions that cannot be expressed are reported as
"condition:<step> -> <text>".

Rebuild one file from a spec (ids from catalog/ghl_ids_<location>.json):
    python3 -m upwork_gen.compile_ghl <spec.json> <out.ghl.json>
"""

from __future__ import annotations

import datetime as _dt
import random
import re
import string
import uuid
import warnings as _warnings
from typing import Any, Dict, List, Optional, Set, Tuple

from .compile_ghl_prompt import _node_op, _check_params, _strip_step, TRIGGER_OPS
from .params import for_wait
from .spec import SpecError, WorkflowSpec, Node, Edge

TRIGGER_TYPES = {
    "form_submitted": "form_submission",          # VERIFIED (export)
    "survey_submitted": "survey_submission",
    "customer_replied": "customer_replied",
    "contact_created": "contact_created",
    "contact_tag_added": "contact_tag",           # VERIFIED (export 2026-09-23)
    "contact_tag_removed": "contact_tag",         # VERIFIED (export 2026-09-23)
    "pipeline_stage_changed": "pipeline_stage_changed",
    "opportunity_created": "opportunity_created",
    "opportunity_status_changed": "opportunity_status_changed",
    # UNVERIFIED: sources disagree between "appointment" and "appointment_status".
    "appointment_status": "appointment",
    "inbound_webhook": "inbound_webhook",
    "missed_call": "call_status",
    "invoice_paid": "invoice",
    "order_submitted": "order_submitted",
    "birthday": "birthday_reminder",
    "task_completed": "task_completed",
}

class GHLCompileWarning(UserWarning):
    """A compiled step a human must check after import (the file is still written)."""


# The AI step's defaults when the spec does not set them: the values GHL saved on
# the hand-added "GPT powered by OpenAI" step (reference export, 2026-09-23).
AI_DEFAULT_MODEL = "gpt-5-mini"
AI_DEFAULT_TEMPERATURE = "0.2"
# A task assignee that means the contact's assigned user (GHL: "contact.assigned_user"):
# only the explicit phrasings ("assigned user", "contact owner", "contact's owner",
# "the contact's assigned user"). Any other person or role ("the business owner",
# "the sales rep") is looked up as `user:<name>` and warned about when missing.
_ASSIGNED_USER = re.compile(
    r"^(?:the\s+)?(?:contact(?:'s|\u2019s)?\s+)?assigned\s+user$|^(?:the\s+)?contact(?:'s|\u2019s)?\s+owner$",
    re.IGNORECASE)

# GHL's wait picker renders only these (RESEARCH: "hours" imports blank).
WAIT_UNITS = ("minutes", "hour", "days")
_WAIT_ALIASES = {
    "minute": "minutes", "minutes": "minutes", "min": "minutes", "mins": "minutes",
    "hour": "hour", "hours": "hour", "hr": "hour", "hrs": "hour",
    "day": "days", "days": "days",
}

_YES = ("true", "yes")
_NO = ("false", "no")
# A single quote only opens a quote when no letter touches it, so the
# apostrophe in "doesn't" is not read as one.
_QUOTED = re.compile(r"\"([^\"]+)\"|(?<!\w)'([^']+)'(?!\w)")
# A quote mark left once the pairs above are taken out: an unpaired straight
# quote, a straight single quote that is not an in-word apostrophe, or any
# typographic quote or apostrophe (“hot”, ‘hot’, doesn’t, «hot», `hot`). The
# negation reader (_NEGATION) only knows straight apostrophes, so a condition
# holding one of these is never read as a sure tag list.
_STRAY_QUOTE = re.compile(r"[\"`\u00b4\u2018-\u201f\u00ab\u00bb\u2039\u203a\uff02]|(?<!\w)'|'(?!\w)")
_TAG_WORD = re.compile(r"\btags?\b", re.IGNORECASE)
# Words allowed between a tag word and the quoted tag it tests
# (`tag includes "x"`, `does not have tag "x"`, `tags contain any of "x"`,
# `tags include both "x"`, `tag in ["x"`).
_TAG_PREDICATE_WORDS = (
    r"is|are|has|have|had|includes?|contains?|equals?|matches|not|no|does|"
    r"doesn't|doesn’t|do|don't|don’t|any|all|both|one|of|the|a|named|called|in|excludes?|"
    r"with|without|missing|lacks?|either")
_TAG_PREDICATE = re.compile(
    r"(?:\s|:|\[|\(|!?==?|\b(?:" + _TAG_PREDICATE_WORDS + r")\b)*", re.IGNORECASE)
# What may sit between two quoted tags of one list
# (`"a", "b" or "c"`, `"a" (or "b")`, `"a" || "b"`, `"a" and "b"`).
_TAG_LIST_SEP = re.compile(r"(?:\s|,|/|&&?|\|\|?|\(|\)|\b(?:or|and)\b)*", re.IGNORECASE)
_TAG_AFTER = re.compile(r"[\s)\]]*tags?\b", re.IGNORECASE)
# Nouns for something other than the contact's tags. A quoted value that no
# tag word claims is passed over as "not a tag" only when one of these names
# what it belongs to (`opportunity stage is "Won"`, `email contains "@x"`,
# and, before any tag list, `"Won" stage`); any other quoted value makes the
# tag list uncertain.
_OTHER_SUBJECT_WORDS = (
    r"stages?|status(?:es)?|pipelines?|opportunit(?:y|ies)|deals?|e-?mails?|phones?|numbers?|"
    r"fields?|sources?|names?|values?|amounts?|prices?|dates?|birthdays?|calendars?|appointments?|"
    r"forms?|surveys?|owners?|users?|compan(?:y|ies)|address(?:es)?|cit(?:y|ies)|states?|"
    r"countr(?:y|ies)|zip|postal|timezones?|websites?|urls?|domains?|workflows?|campaigns?|"
    r"invoices?|payments?|orders?|products?|types?|scores?|reasons?")
_OTHER_SUBJECT = re.compile(r"\b(?:" + _OTHER_SUBJECT_WORDS + r")\b", re.IGNORECASE)
_OTHER_SUBJECT_AFTER = re.compile(r"[\s)\]]*(?:" + _OTHER_SUBJECT_WORDS + r")\b", re.IGNORECASE)
# All that may join another subject's value to the value it is given
# (`custom field "Lead Type" is "commercial"`): the second value is the same
# subject's, never a tag. No clause break, so `stage "Won" and also "b"` is
# not one.
_VALUE_JOIN = re.compile(r"(?:\s|:|!?==?|\b(?:is|are|was|equals?|not)\b)*", re.IGNORECASE)
# Where one clause of a condition ends and the next begins.
_CLAUSE_BREAK = re.compile(
    r"[,;]|&&?|\|\|?|\b(?:and|or|but|nor|while|whereas|then|unless|except|also|plus|yet)\b",
    re.IGNORECASE)
_NEGATION = re.compile(r"\b(not|doesn't|does not|without|no|lacks|missing)\b|!=|\bexcludes?\b",
                       re.IGNORECASE)
_REPLIED = re.compile(r"\brepl(y|ied|ies)\b", re.IGNORECASE)


def _short_id(n: int = 20) -> str:
    # Trigger ids in the real export are 20-char alphanumerics, not uuids.
    return "".join(random.choice(string.ascii_letters + string.digits) for _ in range(n))


def _uuid() -> str:
    return str(uuid.uuid4())


def _owners() -> Dict[str, Any]:
    return {"assignedOwners": ["contact_owner"],
            "alsoNotifyContactFollowers": False,
            "alsoNotifyOpportunityFollowers": False}


def _looks_like_address(to: str) -> bool:
    return "@" in to or to.strip().startswith("{{")


def _wait_value(node: Node) -> Tuple[int, str]:
    """(amount, unit) with the unit in GHL's spelling. Weeks become days."""
    p = node.params
    amount, unit = p.get("amount"), p.get("unit")
    if amount is None or not unit:
        parsed = for_wait(node)
        if amount is None:
            amount = parsed.get("amount", 1)
        if not unit:
            unit = parsed.get("unit", "days")
    amount = int(amount)
    u = str(unit).strip().lower()
    if u in ("week", "weeks"):
        return amount * 7, "days"
    if u in ("second", "seconds", "sec", "secs"):
        return max(1, (amount + 59) // 60), "minutes"
    if u not in _WAIT_ALIASES:
        raise SpecError("node {!r}: wait unit {!r} is not one GHL accepts (minutes, hours, days, weeks)".format(
            node.key, unit))
    return amount, _WAIT_ALIASES[u]


def _last_clause(text: str) -> str:
    """The part of `text` after its last clause break."""
    end = 0
    for m in _CLAUSE_BREAK.finditer(text):
        end = m.end()
    return text[end:]


def _first_clause(text: str) -> str:
    """The part of `text` before its first clause break."""
    m = _CLAUSE_BREAK.search(text)
    return text[:m.start()] if m else text


def _tag_param_problem(tag: Any) -> Optional[str]:
    """Why an If/Else `params.tag` is not a tag name or a list of tag names."""
    items = tag if isinstance(tag, list) else [tag]
    if tag is None or all(isinstance(t, str) for t in items):
        return None
    return "`tag` must be a tag name or a list of tag names, got {!r}".format(tag)


def condition_tags(node_params: Optional[Dict[str, Any]], condition_text: Any) -> Optional[List[str]]:
    """The tag names an if_else tests. Shared with ghl_prereqs so both read a
    condition the same way.

    params.tag (a string or a list of strings) wins; any other type is a
    SpecError. Otherwise the quoted strings are grouped into lists (quotes
    joined only by `,` `or` `and` `/` `||` `&&` `(` `)`), and every list must
    be one of two things:

    - tied to tags: right after a tag word and its predicate (`contact tag
      includes "a"`, `tag in ["a", "b"]`, `tags include both "a" and "b"`) or
      directly before a tag word (`has "a" or "b" tag`). The whole list counts.
    - another subject's value: a noun such as stage, status, pipeline or email
      names it in its own clause, in the text before it (`and opportunity
      stage is "Won"`, `email contains "@gmail.com"`, `field "Lead Type" is
      "commercial"`) or, only while no tag list has been found, right after
      it (`"Won" stage and has tag "a"`). It is passed over.

    None whenever the reader cannot be sure, so the caller treats the
    condition as unresolved and never acts on a subset: a quoted value that is
    neither (`has tag "hot" but not "cold"`, `tag is "a" or is "b"`), a value
    after a tag list that only a noun after it names (`has tag "a" and is not
    in the "Closed" stage`), a tag list that also reads as another subject's
    value (`tag is "a" or "Won" stage`), a tag word tied to no quote (`tag
    score is "a"`, `and no other tags`, `has the vip tag`), or a quote mark it
    cannot pair (`“hot”`, `"a" or "b`). [] only when the condition names no
    tags at all."""
    params = node_params or {}
    problem = _tag_param_problem(params.get("tag"))
    if problem:
        raise SpecError(problem)
    if params.get("tag"):
        tags = params["tag"]
        return list(tags) if isinstance(tags, list) else [tags]
    text = str(condition_text or "")
    quotes = list(_QUOTED.finditer(text))
    unquoted = list(text)
    for q in quotes:
        unquoted[q.start():q.end()] = " " * (q.end() - q.start())
    if _STRAY_QUOTE.search("".join(unquoted)):
        return None  # a quote mark this reader cannot pair: never guess
    runs: List[List[Any]] = []
    for q in quotes:
        if runs and _TAG_LIST_SEP.fullmatch(text[runs[-1][-1].end():q.start()]):
            runs[-1].append(q)
        else:
            runs.append([q])

    found: List[str] = []
    pos = 0  # the text before pos is accounted for
    other = False  # the list just before pos was another subject's value
    for i, run in enumerate(runs):
        start, end = run[0].start(), run[-1].end()
        upto = runs[i + 1][0].start() if i + 1 < len(runs) else len(text)
        rest = text[pos:start]
        words = list(_TAG_WORD.finditer(rest))
        by_predicate = bool(words) and _TAG_PREDICATE.fullmatch(rest[words[-1].end():]) is not None
        tail = _TAG_AFTER.match(text, end)
        untied = words[:-1] if by_predicate else words
        if untied:
            return None  # a tag word tied to no quote (`tag score is "a"`)
        if by_predicate or tail:
            after = tail.end() if tail else end
            if _OTHER_SUBJECT.search(_first_clause(text[after:upto])) or \
                    (not by_predicate and _OTHER_SUBJECT.search(_last_clause(rest))):
                return None  # the list also reads as another subject's value
            values = [q.group(1) if q.group(1) is not None else q.group(2) for q in run]
            if not all(v.strip() for v in values):
                return None  # a blank tag name (`tag is " "`)
            found.extend(values)
            pos, other = after, False
        elif _OTHER_SUBJECT.search(_last_clause(rest)) or (other and _VALUE_JOIN.fullmatch(rest)) or \
                (not found and _OTHER_SUBJECT_AFTER.match(text, end)):
            # another subject's value: the text before it names the subject
            # (`stage is "Won"`, `field "Lead Type" is "commercial"`), or,
            # while no tag list has been found yet, the word right after it
            # does (`"Won" stage and has tag "a"`). After a tag list only the
            # text between counts: in `has tag "a" and is not in the "Closed"
            # stage` that text is `and is not in the`, which names nothing,
            # so the list is not sure (and its "not" is the stage's).
            pos, other = end, True
        else:
            return None  # a quoted value no tag word or subject claims: maybe a tag
    if _TAG_WORD.search(text[pos:]):
        return None  # tag talk after the last list (`and no other tags`, `"a" lead tag`)
    return found


# Ops whose params name a pipeline and stage. ghl_prereqs uses the same set.
PIPELINE_OPS = ("pipeline_stage_changed", "opportunity_created", "opportunity_status_changed",
                "create_opportunity", "update_opportunity")
# Ops whose `tag` names contact tags (one tag name or a list of them).
TAG_PARAM_OPS = ("contact_tag_added", "contact_tag_removed", "add_tag", "remove_tag", "goal", "if_else")
# Ops that act on exactly one tag: a list would compile to a nested tag list.
ONE_TAG_OPS = ("add_tag", "remove_tag", "goal")
# A gate sentence that reads negative. With params.tag and no `negate`, such a
# sentence would compile as a positive test, so it must say which it means.
# Read on the sentence with its quoted spans blanked (_unquoted), so a tag
# named "without-reply" is not a negation. Negative is anything _NEGATION
# counts (not, no, without, lacks, missing, excludes, !=, ...) plus the n't
# forms (isn't, don't, hasn't, won't, ...; straight or curly apostrophe) and
# the words never, absent, removed, lacking, lack, lacked, untagged, excluding
# and excluded, and the apostrophe-less doesnt, dont, isnt, hasnt, havent and
# didnt. A false alarm only costs the builder an explicit `"negate": false`.
# Gates without params.tag read their direction from this too (_tag_condition,
# _reply_condition), unless they carry an explicit boolean negate.
_NEGATIVE_SENTENCE = re.compile(
    r"\b\w+n['\u2019]t\b|\bnot\s+tagged\b|\b(?:never|absent|removed|lacking|lack|lacked|untagged"
    r"|excluding|excluded|doesnt|dont|isnt|hasnt|havent|didnt)\b", re.IGNORECASE)


def _unquoted(text: str) -> str:
    """text with every quoted span (paired the way condition_tags pairs them)
    blanked to spaces."""
    chars = list(text)
    for q in _QUOTED.finditer(text):
        chars[q.start():q.end()] = " " * (q.end() - q.start())
    return "".join(chars)


def _negative_word(condition: Any) -> Optional[str]:
    """The first word (or operator) that makes a gate sentence read negative,
    outside its quoted spans, or None."""
    text = _unquoted(str(condition or ""))
    hits = [m for m in (_NEGATION.search(text), _NEGATIVE_SENTENCE.search(text)) if m]
    if not hits:
        return None
    return min(hits, key=lambda m: m.start()).group(0)


def _reads_negative(condition: Any) -> bool:
    """True when a gate sentence, outside its quoted spans, reads negative."""
    return _negative_word(condition) is not None
# The param that names a contact custom field, per op.
FIELD_PARAMS = {"update_contact_field": "field", "ai_step": "output_field"}


def name_param_problem(op: str, params: Any) -> Optional[str]:
    """Why a param whose value ghl_prereqs creates a GHL object under is not a
    name, or None. Those params are every one it reads a name from: a
    pipeline op's `pipeline`, `stage` and each entry of `stages`; the `tag` of
    a tag step or trigger, a goal and an If/Else; update_contact_field's
    `field` and ai_step's `output_field`. (Merge-field keys come from string
    text only.) ghl_prereqs (exit 2, before any call), compile_ghl and the
    builder prompt (SpecError) all refuse a spec this objects to, so none of
    them ever names an object after a dict, a list, a bool or a number.
    add_tag, remove_tag and goal take one tag (a list compiled to a nested
    tag list), and an If/Else with `tag`, no `negate` and a sentence that
    reads negative must say `negate` explicitly."""
    p = params if isinstance(params, dict) else {}
    if op in PIPELINE_OPS:
        for key in ("pipeline", "stage"):
            value = p.get(key)
            if value is not None and not isinstance(value, str):
                return "`{0}` must be a {0} name (a string), got {1!r}".format(key, value)
        if "stages" in p:
            stages = p["stages"]
            if not isinstance(stages, list):
                return "`stages` must be a list of stage names in pipeline order, got {!r}".format(stages)
            for stage in stages:
                if not isinstance(stage, str):
                    return "every entry in `stages` must be a stage name, got {!r}".format(stage)
    if op in ONE_TAG_OPS and p.get("tag") is not None and not isinstance(p["tag"], str):
        return "`tag` must be one tag name (a string), got {!r}: one tag per step; use two steps".format(
            p["tag"])
    if op in TAG_PARAM_OPS:
        problem = _tag_param_problem(p.get("tag"))
        if problem:
            return problem
    if op == "if_else" and "negate" in p and p["negate"] is not None and \
            not isinstance(p["negate"], bool):
        return "`negate` must be true, false or null, got {!r}".format(p["negate"])
    if op == "if_else" and p.get("tag") and p.get("negate") is None:
        word = _negative_word(p.get("condition", ""))
        if word is not None:
            return ("the condition reads negative ({!r}) but `negate` is not set, so it would compile "
                    "as a positive tag test; set \"negate\": true, or \"negate\": false if the gate "
                    "is a positive test (straight quotes around tag names avoid false alarms)".format(word))
    key = FIELD_PARAMS.get(op)
    if key is not None:
        value = p.get(key)
        if value is not None and not isinstance(value, str):
            return "`{}` must be a custom field name (a string), got {!r}".format(key, value)
    return None


def _tag_condition(params: Dict[str, Any]) -> Optional[Tuple[List[str], bool]]:
    """(tags, negated) when an if_else condition is about contact tags."""
    text = str(params.get("condition", ""))
    tags = condition_tags(params, text)
    if not tags:
        return None
    if params.get("tag"):
        return tags, bool(params.get("negate", False))
    negate = params.get("negate")
    if isinstance(negate, bool):
        # An explicit negate decides the test; the sentence is not read.
        return tags, negate
    return tags, _reads_negative(text)


def _goto_attrs(target: str) -> Tuple[str, Dict[str, Any], Dict[str, Any]]:
    """The Go To record (op go_to and loop edges); targetNodeId is filled in
    after the whole chain is emitted. VERIFIED: key set and `type` as GHL's
    builder wrote them in reference/ghl_export_reference_all_types.json.
    UNVERIFIED: whether GHL accepts a target in another If/Else branch
    (_check_goto_branch warns).
    targetNodeName is a human mirror of targetNodeId: the importer
    (stripAnnotations) drops it before writing, as it does every *Name key."""
    return "goto", {"targetNodeId": "", "type": "goto", "targetNodeName": target}, {}


def _reply_condition(text: str, negate: Any = None) -> Optional[bool]:
    """True/False when the condition asks whether the contact replied. An
    explicit boolean `negate` (the gate's params.negate) decides the test;
    only when it is absent or null is the sentence read for polarity."""
    if not _REPLIED.search(text):
        return None
    if isinstance(negate, bool):
        return not negate
    return not _reads_negative(text)


class GHLCompiler:
    def __init__(self, spec: WorkflowSpec, ids: Optional[Dict[str, str]] = None,
                 location_id: str = "", workflow_id: Optional[str] = None):
        self.spec = spec
        self.ids = ids or {}
        self.location_id = location_id
        self.workflow_id = workflow_id or _uuid()
        self.nodes: Dict[str, Node] = {n.key: n for n in spec.nodes if not n.is_ai_sub}
        self.out: List[Dict[str, Any]] = []
        self.refs: Dict[str, str] = {}
        self.unresolved: List[str] = []
        # Checks for a human after import (see _warn); not unresolved ids.
        self.warnings: List[str] = []
        self.first_id: Dict[str, str] = {}
        # (goto record, target text, target is a node key from a loop edge)
        self.gotos: List[Tuple[Dict[str, Any], str, bool]] = []
        self.outgoing: Dict[str, List[Tuple[str, Optional[str]]]] = {}
        # Loop edges, emitted as Go To steps.
        self.loops: Dict[str, List[Tuple[str, Optional[str]]]] = {}
        for e in spec.edges:
            (self.loops if e.loop else self.outgoing).setdefault(e.src, []).append((e.dst, e.branch))
        self.ops = {k: _node_op(n) for k, n in self.nodes.items()}
        for k, n in self.nodes.items():
            _check_params(n, self.ops[k])
            problem = name_param_problem(self.ops[k], n.params)
            if problem:
                raise SpecError("node {!r} ({}): {}".format(k, _strip_step(n.label), problem))
        self._check_linear()
        self._check_loops()

    # -- structure -----------------------------------------------------------
    def _is_trigger(self, key: str) -> bool:
        return self.nodes[key].is_trigger or self.ops[key] in TRIGGER_OPS

    def _check_linear(self) -> None:
        for key, outs in self.outgoing.items():
            if key not in self.nodes:
                continue
            op = self.ops[key]
            label = _strip_step(self.nodes[key].label)
            if op == "if_else":
                yes = [o for o in outs if (o[1] or "").lower() in _YES]
                no = [o for o in outs if (o[1] or "").lower() in _NO]
                if len(yes) + len(no) != len(outs):
                    raise SpecError(
                        "node {!r} ({}): every edge out of an if_else needs branch \"true\" or \"false\"".format(
                            key, label))
                if len(yes) > 1 or len(no) > 1:
                    raise SpecError(
                        "node {!r} ({}): an if_else has one true and one false branch; put the extra "
                        "steps one after another inside the branch".format(key, label))
                continue
            if len(outs) > 1:
                what = "trigger" if self._is_trigger(key) else "step"
                raise SpecError(
                    "node {!r} ({}): this {} has {} next steps ({}), but a GHL workflow runs one step "
                    "after another. Use a flow.branch (if_else) to split, or move the extra path into "
                    "its own workflow.".format(key, label, what, len(outs), ", ".join(o[0] for o in outs)))
            if outs and op == "end":
                raise SpecError("node {!r} ({}): `end` stops the chain, so nothing can follow it".format(key, label))
            if outs and op == "go_to":
                raise SpecError("node {!r} ({}): `go_to` jumps away, so nothing can follow it".format(key, label))

    def _check_loops(self) -> None:
        """A loop edge becomes a Go To at the end of its source's chain (or of
        one if_else branch). Anything that would need a step after that Go To,
        or a Go To out of a trigger, `end` or `go_to`, cannot be built."""
        for key, loops in self.loops.items():
            if key not in self.nodes:
                continue
            op = self.ops[key]
            label = _strip_step(self.nodes[key].label)
            for dst, _b in loops:
                if dst not in self.nodes:
                    raise SpecError("node {!r} ({}): loop edge to unknown node {!r}".format(key, label, dst))
                if self._is_trigger(dst):
                    raise SpecError("node {!r} ({}): a loop back to trigger {!r} cannot be a GHL Go To; "
                                    "point it at the first action instead".format(key, label, dst))
            if self._is_trigger(key) or op in ("end", "go_to"):
                raise SpecError("node {!r} ({}): a loop edge becomes a Go To step, which cannot follow "
                                "{}".format(key, label, "a trigger" if self._is_trigger(key) else "`{}`".format(op)))
            outs = self.outgoing.get(key, [])
            if op == "if_else":
                taken = {(o[1] or "").lower() in _YES for o in outs}
                seen: Set[bool] = set()
                for dst, b in loops:
                    arm = (b or "").lower()
                    if arm not in _YES + _NO:
                        raise SpecError("node {!r} ({}): a loop edge out of an if_else needs branch \"true\" "
                                        "or \"false\"".format(key, label))
                    is_yes = arm in _YES
                    if is_yes in taken or is_yes in seen:
                        raise SpecError("node {!r} ({}): the {} branch already has a next step, so the loop "
                                        "back to {!r} has nowhere to go; a Go To must be the last step of its "
                                        "branch".format(key, label, "true" if is_yes else "false", dst))
                    seen.add(is_yes)
                continue
            if len(loops) > 1:
                raise SpecError("node {!r} ({}): {} loop edges ({}), but only one Go To can end a "
                                "step's chain".format(key, label, len(loops), ", ".join(d for d, _b in loops)))
            if outs:
                raise SpecError("node {!r} ({}): the loop back to {!r} becomes a Go To, which ends the chain, "
                                "so this step cannot also continue to {}".format(
                                    key, label, loops[0][0], ", ".join(o[0] for o in outs)))

    def _follow(self, key: Optional[str]) -> Optional[str]:
        """The next step to emit, or None when the chain ends here (`end`)."""
        if key is None or self.ops.get(key) == "end":
            return None
        return key

    def _next_of(self, key: str) -> Optional[str]:
        outs = self.outgoing.get(key, [])
        return self._follow(outs[0][0]) if outs else None

    # -- ids ---------------------------------------------------------------
    def _lookup(self, kind: str, name: str) -> str:
        found = self.ids.get("{}:{}".format(kind, name))
        if not found:
            self.unresolved.append("{}:{}".format(kind, name))
            return "UNRESOLVED-{}-{}".format(kind, name.replace(" ", "_"))
        self.refs[found] = name
        return found

    # -- triggers ------------------------------------------------------------
    def _trigger_conditions(self, t: Node, op: str) -> List[Dict[str, Any]]:
        p = t.params
        if op in ("contact_tag_added", "contact_tag_removed"):
            # VERIFIED (both): GHL re-created these triggers with its own ids and
            # read the conditions back unchanged (reference/ghl_export_reference_all_types.json).
            added = op.endswith("added")
            return [{"field": "tagsAdded" if added else "tagsRemoved", "operator": "index-of-true",
                     "value": p["tag"], "title": "Tag Added" if added else "Tag Removed",
                     "type": "select", "id": "tag-added" if added else "tag-removed"}]
        if op == "form_submitted" and p.get("form"):
            # RESEARCH: filter only when the form exists in the id map.
            fid = self.ids.get("form:{}".format(p["form"]))
            if not fid:
                self.unresolved.append("form:{}".format(p["form"]))
                return []
            self.refs[fid] = p["form"]
            return [{"field": "formId", "operator": "==", "value": fid, "title": "Form Is",
                     "type": "select", "id": "form"}]
        return []

    # -- attributes per op --------------------------------------------------
    # "VERIFIED (export 2026-09-23)" = GHL's builder saved this shape in
    # reference/ghl_export_reference_all_types.json after the step was checked
    # (and, where it was broken, fixed) by hand.
    def _attrs(self, node: Node, op: str) -> Tuple[str, Dict[str, Any], Dict[str, Any]]:
        """(node type, attributes, extra node-level keys)."""
        p = node.params
        name = _strip_step(node.label)
        if op == "add_tag":                                   # VERIFIED
            return "add_contact_tag", {"tags": [p["tag"]]}, {}
        if op == "remove_tag":                                # VERIFIED
            return "remove_contact_tag", {"tags": [p["tag"]]}, {}
        if op == "send_sms":                                  # VERIFIED
            a = {"body": p["message"]}; a.update(_owners()); return "sms", a, {}
        if op == "send_email":                                # VERIFIED, `body` too (export 2026-09-23)
            a = {"subject": p["subject"], "html": p["body"], "body": p["body"],
                 "from_name": p.get("from_name", ""), "from_email": p.get("from_email", ""),
                 "cc": "", "bcc": "", "preHeader": p.get("preheader", "")}
            a.update(_owners()); return "email", a, {}
        if op == "wait":                                      # VERIFIED, unit "hour" too (export 2026-09-23)
            amount, unit = _wait_value(node)
            return "wait", {"type": "time", "convertToMultipath": False, "hybridActionType": "wait",
                            "isHybridAction": True, "name": name, "cat": "action",
                            "transitions": [], "startAfter": {"when": "after", "type": unit, "value": amount},
                            "timePeriodInputMode": "standard", "unitInputMode": "standard"}, {}
        if op == "create_opportunity":                        # VERIFIED, FIELD
            pid = self._lookup("pipeline", p["pipeline"])
            sid = self._lookup("stage", "{}/{}".format(p["pipeline"], p["stage"]))
            return "create_opportunity", {
                "pipeline_id": pid, "pipeline_stage_id": sid,
                "opportunity_name": p.get("name", "{{contact.name}}"),
                "opportunity_source": p.get("source", ""),
                "monetary_value": str(p.get("value", "")),
                "opportunity_status": p.get("status", "open"),
                "pipeline_name": p["pipeline"], "pipeline_stage_name": p["stage"]}, {}
        if op == "update_opportunity":                        # VERIFIED (export 2026-09-23)
            # The export's pipelineName and valueName are the exporter's name mirrors of
            # pipelineId / value; the importer strips them, so they are not emitted.
            pid = self._lookup("pipeline", p["pipeline"])
            sid = self._lookup("stage", "{}/{}".format(p["pipeline"], p["stage"]))
            status = p.get("status", "open")
            return "internal_update_opportunity", {
                "type": "internal_update_opportunity", "allowBackward": True, "pipelineId": pid,
                "__customInputFields__": [{"filterField": "pipelineStageId", "value": sid,
                                           "dataType": "SINGLE_OPTIONS", "valueFieldType": "select",
                                           "__customInputs__": {}}],
                "__customInputs__": {},
                "DYNAMIC": "Update opportunity to '{}' stage with status {} in '{}' pipeline".format(
                    p["stage"], status, p["pipeline"]),
                "pipeline_name": p["pipeline"], "pipeline_stage_name": p["stage"]}, {"workflowsActionType": "INTERNAL"}
        if op == "call":                                      # VERIFIED
            return "call", {"timeout": int(p.get("timeout_seconds", 30)), "whisper_message": p["whisper"],
                            "disable_detect_voicemail": False, "call_connect": True}, {}
        if op == "internal_notification":
            # VERIFIED: all three variants (export 2026-09-23). The custom_email variant
            # (`to` is an address) is still RESEARCH.
            kind = p["type"]
            outer: Dict[str, Any] = {"type": None, "email": None, "sms": None, "userType": "assign",
                                     "whatsapp": None, "notification": None}
            if kind == "sms":
                sms: Dict[str, Any] = {"userType": "assign"}; sms.update(_owners()); sms["body"] = p["message"]
                outer.update({"type": "sms", "sms": sms})
            elif kind == "email":
                to = str(p.get("to", ""))
                subject = p.get("subject", name)
                if _looks_like_address(to):
                    em: Dict[str, Any] = {"userType": "custom_email", "to": to}
                else:
                    em = {"userType": "assign"}; em.update(_owners())
                em.update({"subject": subject, "html": p["message"]})
                outer.update({"type": "email", "email": em, "userType": em["userType"]})
            else:
                notif: Dict[str, Any] = {"title": name, "body": p["message"], "redirectPage": "contact",
                                         "userType": "assign"}
                notif.update(_owners())
                outer.update({"type": "notification", "notification": notif})
            return "internal_notification", outer, {}
        if op == "goal":
            # Top-level keys VERIFIED; the tag goal_condition VERIFIED (export 2026-09-23).
            # form / appointment / other goal conditions are RESEARCH.
            gt = p["goal_type"]
            cond: Dict[str, Any]
            if gt in ("tag_added", "tag_removed"):
                cond = {"goal_condition": "add_contact_tag" if gt == "tag_added" else "remove_contact_tag",
                        "extras": {"tags": [p["tag"]]}}
            elif gt == "email_event":
                cond = {"goal_condition": "email_event", "extras": {"stepIds": [], "event_types": []}}
            elif gt == "form_submitted":
                cond = {"goal_condition": "form_submitted", "extras": {"forms": [p.get("form", "")]}}
            elif gt == "appointment_status":
                cond = {"goal_condition": "appointment", "extras": {"status": p.get("status", "confirmed")}}
            else:
                cond = {"goal_condition": gt, "extras": {}}
            cond["id"] = _uuid()
            return "workflow_goal", {"op": "or", "segments": [{"op": "or", "conditions": [cond]}],
                                     "type": "workflow_goal",
                                     "action": "exit" if p.get("if_not_met", "end") == "end" else "continue"}, {}
        if op == "manual_action":
            # The export's hand-off task is an `add_notes` step (VERIFIED keys); a true
            # manual-call action type has not been seen in an export yet. The 2026-09-23
            # export has a colour and an attributes `type` here, but GHL's own 2026-09-21
            # export has color null and no `type`, so neither is adopted.
            return "add_notes", {"html": p.get("instructions", ""), "title": p.get("title", name),
                                 "color": None}, {}
        if op == "create_task":                               # VERIFIED (export 2026-09-23)
            # Adopted from the export: dueDate and assignedTo (the panel's due date and
            # assignee, which had to be set by hand after the first import) and the
            # node-level workflowsActionType + stepIndex (the only node keys GHL added;
            # the task had no icon after the first import). Not adopted: an empty
            # __customInputs__. The due/assignee line stays in `body` as before.
            due = int(p.get("due_in_days", 1))
            assign_to = p.get("assign_to", "the contact's assigned user")
            due_line = "Due in {} day{}. Assign to: {}.".format(due, "" if due == 1 else "s", assign_to)
            body = "{}\n\n{}".format(p["description"], due_line) if p.get("description") else due_line
            a = {"type": "task_notification", "title": p["title"], "body": body}
            assignee = self._task_assignee(name, assign_to)
            if assignee:
                a["assignedTo"] = assignee
            a["dueDate"] = {"duration": due, "unit": "days", "skipWeekends": False}
            return "task-notification", a, {"workflowsActionType": "INTERNAL", "stepIndex": 1}
        if op == "update_contact_field":                      # VERIFIED (export 2026-09-23)
            # GHL's shape is a `fields` list keyed by the custom field's id (from the id
            # map, `field:<name>`). Not adopted: fieldName, the exporter's mirror of
            # `field`. `type` is the field's data type; the id map does not carry it, so it
            # is "string" (what the export shows for a text field). UNVERIFIED for number,
            # date and option fields: set the type after import if the value is not text.
            return "update_contact_field", {
                "type": "update_contact_field", "actionType": "update_field_data",
                "fields": [{"field": self._lookup("field", p["field"]), "value": p["value"],
                            "title": p["field"], "type": "string", "date": ""}]}, {}
        if op == "assign_user":                               # VERIFIED for one user (export 2026-09-23)
            # user_list holds GHL user ids, which are per location: they come only from the
            # id map (`user:<name>`), never from this file. The export's round-robin
            # bookkeeping (traffic_weightage, traffic_index, total_index) is derived from
            # user_list the way it shows for one user; for several users it is UNVERIFIED.
            users = self._assign_users(name, p.get("user"))
            return "assign_user", {
                "only_unassigned_contact": False, "total_index": len(users), "traffic_split": "equally",
                "traffic_weightage": {u: 1 for u in users},
                "traffic_index": [{"id": u, "indexes": [i + 1]} for i, u in enumerate(users)],
                "user_list": users, "type": "assign_user"}, {}
        if op == "add_to_workflow":                           # VERIFIED (export 2026-09-23)
            # Not adopted: input_trigger_params (true in the export) and an attributes
            # `type` echoing the node type. The first import showed the step working
            # without them.
            return "add_to_workflow", {"workflow_name": p["workflow"],
                                       "workflow_id": self._lookup("workflow", p["workflow"])}, {}
        if op == "remove_from_workflow":                      # VERIFIED (export 2026-09-23)
            return "remove_from_workflow", {"workflow_name": p["workflow"],
                                            "workflow_id": self._lookup("workflow", p["workflow"])}, {}
        if op == "webhook":                                   # VERIFIED (export 2026-09-23)
            return "webhook", {"url": p["url"], "method": p.get("method", "POST")}, {}
        if op == "send_review_request":                       # VERIFIED (export 2026-09-23)
            # The step Lorenzo re-added by hand. review_type "sms" is the export's value
            # (the spec has no channel param); overrideReviewLink "default" uses the
            # location's own review link.
            return "review_request", {"type": "review_request", "overrideReviewLink": "default",
                                      "review_type": "sms"}, {}
        if op == "ai_step":                                   # VERIFIED (export 2026-09-23)
            # GHL's "GPT powered by OpenAI" step as re-added by hand: the whole attribute
            # set, since the compiled guess did not survive import at all. model and
            # temperature default to the export's values unless the spec sets them;
            # temperature is a string, as GHL stores it. apiKey "" means GHL's own key.
            # params.output_field has no key in this shape and is not emitted.
            return "chatgpt", {
                "type": "chatgpt", "apiKey": "", "event": "simple-prompt",
                "model": str(p.get("model", AI_DEFAULT_MODEL)),
                "temperature": str(p.get("temperature", AI_DEFAULT_TEMPERATURE)),
                "promptText": p["prompt"], "actionType": "custom",
                "actionParams": {"message": "", "categories": [], "length": "", "from": "", "to": "",
                                 "memoryKeyToggle": False, "memoryKeyType": "action", "memoryKeyCustom": ""},
                "memoryKey": "", "excludeFromHistory": False, "excludeInstructionsFromHistory": False,
            }, {"stepIndex": 1}
        if op == "go_to":                                     # VERIFIED keys (export 2026-09-23)
            return _goto_attrs(p["target"])
        raise SpecError("compile_ghl: op {!r} not supported yet (node {!r})".format(op, node.key))

    # -- warnings ------------------------------------------------------------
    def _warn(self, message: str) -> None:
        """Something a human must check after import. Kept on self.warnings,
        printed by main() and copied into generate's notes (both catch the
        GHLCompileWarning raised here, so it prints once); other callers see
        it on stderr."""
        if message not in self.warnings:
            self.warnings.append(message)
            _warnings.warn(message, GHLCompileWarning, stacklevel=2)

    def _task_assignee(self, step: str, assign_to: Any) -> Optional[str]:
        """assignedTo for a task: GHL's "contact.assigned_user" for the
        contact's assigned user (the export's value), else a user id from the
        id map (`user:<name>`). Unknown users are left unset, with a warning."""
        text = str(assign_to or "").strip()
        if not text or _ASSIGNED_USER.match(" ".join(text.rstrip(".").split())):
            return "contact.assigned_user"
        uid = self.ids.get("user:{}".format(text))
        if uid:
            self.refs[uid] = text
            return uid
        self._warn("task \"{}\": user {!r} is not in the id map (no `user:{}` entry), so the "
                   "assignee is left unset; pick it after import".format(step, text, text))
        return None

    def _assign_users(self, step: str, user: Any) -> List[str]:
        """user_list for Assign to user: ids from the id map only."""
        names = user if isinstance(user, list) else ([user] if user else [])
        ids: List[str] = []
        missing: List[str] = []
        for n in names:
            uid = self.ids.get("user:{}".format(n))
            if uid:
                self.refs[uid] = str(n)
                ids.append(uid)
            else:
                missing.append(str(n))
        if not names:
            self._warn("assign to user \"{}\": the spec names no user, so user_list is empty; pick the "
                       "users for the round robin after import".format(step))
        elif missing:
            self._warn("assign to user \"{}\": {} not in the id map (no `user:<name>` entry), so "
                       "left out of user_list; add them after import".format(step, ", ".join(missing)))
        return ids

    def _if_else_attrs(self, node: Node, name: str, yes_id: str, yes_name: str,
                       none_name: str) -> Dict[str, Any]:
        """Parent condition-node attributes. Skeleton VERIFIED (export); tag condition VERIFIED (export 2026-09-23)."""
        p = node.params
        conditions: List[Dict[str, Any]] = []
        tag = _tag_condition(p)
        text = str(p.get("condition", ""))
        # The reply check only stands in when the condition names no tags at
        # all ([]); None means tags this reader cannot pin down: unresolved.
        replied = _reply_condition(text, p.get("negate")) if tag is None and condition_tags(p, text) == [] else None
        if tag is not None:
            tags, negated = tag
            conditions.append({"conditionType": "contact_detail", "conditionSubType": "tags",
                               "conditionOperator": "index-of-false" if negated else "index-of-true",
                               "conditionValue": tags})
        elif replied is not None:
            # VERIFIED condition from the export's "Did the Call Connect".
            conditions.append({"conditionType": "contact_reply", "conditionSubType": "contact_replied",
                               "conditionOperator": "==", "conditionValue": "true" if replied else "false"})
        else:
            self.unresolved.append("condition:{} -> {}".format(name, p.get("condition", "")))
        return {"currentRecipeType": "CUSTOM",
                "branches": [{"name": yes_name, "operator": "and",
                              "segments": [{"operator": "and", "conditions": conditions}], "id": yes_id}],
                "if": True, "operator": "and", "conditionName": name, "version": 2,
                "noneBranchName": none_name}

    # -- walking -----------------------------------------------------------
    def _emit(self, key: str, nid: str, prev_id: Optional[str], prev_name: Optional[str],
              branch_id: Optional[str], branch_name: Optional[str], order: int,
              path: Tuple[str, ...] = ()) -> None:
        """Emit node `key` (with id `nid`) and everything after it in its chain."""
        if key in path:
            raise SpecError("GHL workflow loops back to {!r}; use op go_to for a jump".format(key))
        path = path + (key,)
        node = self.nodes[key]; op = self.ops[key]
        name = _strip_step(node.label)
        self.refs[nid] = name
        self.first_id.setdefault(key, nid)
        rec: Dict[str, Any] = {"type": None, "id": nid, "name": name, "attributes": {}, "order": order}
        if prev_id:
            rec["parentKey"] = prev_id; rec["parentKeyName"] = prev_name
        if branch_id:
            rec["parent"] = branch_id; rec["parentName"] = branch_name

        if op == "if_else":
            outs = self.outgoing.get(key, [])
            yes = self._follow(next((o[0] for o in outs if (o[1] or "").lower() in _YES), None))
            no = self._follow(next((o[0] for o in outs if (o[1] or "").lower() in _NO), None))
            yes_id, none_id = _uuid(), _uuid()
            yes_name = node.params.get("true_label", "Yes")
            none_name = node.params.get("false_label", "None")
            self.refs[yes_id] = yes_name; self.refs[none_id] = none_name
            rec["type"] = "if_else"
            rec["attributes"] = self._if_else_attrs(node, name, yes_id, yes_name, none_name)
            rec["nodeType"] = "condition-node"; rec["cat"] = "conditions"
            rec["next"] = [yes_id, none_id]; rec["nextNames"] = [yes_name, none_name]
            self.out.append(rec)
            for bid, bname, arm, kind in ((yes_id, yes_name, yes, "branch-yes"),
                                          (none_id, none_name, no, "branch-no")):
                sib = [x for x in (yes_id, none_id) if x != bid]
                b: Dict[str, Any] = {"type": "if_else", "id": bid, "name": bname, "parentKey": nid, "parent": nid,
                                     "nodeType": kind, "cat": "conditions", "sibling": sib,
                                     "attributes": ({"else": True} if kind == "branch-no" else
                                                    {"if": False, "conditionName": "Condition", "operator": "and",
                                                     "branches": []}),
                                     "order": order + 1, "parentKeyName": name, "parentName": name,
                                     "siblingNames": [self.refs[x] for x in sib]}
                loop = next((d for d, lb in self.loops.get(key, [])
                             if ((lb or "").lower() in _YES) == (kind == "branch-yes")), None)
                arm_id = _uuid() if (arm or loop) else None
                if arm:
                    b["next"] = arm_id; b["nextName"] = _strip_step(self.nodes[arm].label)
                elif loop:
                    b["next"] = arm_id; b["nextName"] = self._loop_goto_name(loop)
                self.out.append(b)
                if arm:
                    self._emit(arm, arm_id, bid, bname, bid, bname, 0, path)
                elif loop:
                    self._emit_loop_goto(loop, arm_id, bid, bname, bid, bname, 0)
            return

        rec["type"], rec["attributes"], extra = self._attrs(node, op)
        rec.update(extra)
        if op == "go_to":
            self.gotos.append((rec, node.params["target"], False))
        nxt = self._next_of(key)
        loops = self.loops.get(key, [])
        loop = loops[0][0] if loops and not nxt else None
        nxt_id = _uuid() if (nxt or loop) else None
        if nxt:
            rec["next"] = nxt_id; rec["nextName"] = _strip_step(self.nodes[nxt].label)
        elif loop:
            rec["next"] = nxt_id; rec["nextName"] = self._loop_goto_name(loop)
        else:
            rec["next"] = ""
        self.out.append(rec)
        if nxt:
            self._emit(nxt, nxt_id, nid, name, branch_id, branch_name, order + 1, path)
        elif loop:
            self._emit_loop_goto(loop, nxt_id, nid, name, branch_id, branch_name, order + 1)

    def _loop_goto_name(self, target_key: str) -> str:
        # Same wording as the builder prompt: "add action Go To pointing at ...".
        return "Go To {}".format(_strip_step(self.nodes[target_key].label))

    def _emit_loop_goto(self, target_key: str, nid: str, prev_id: str, prev_name: str,
                        branch_id: Optional[str], branch_name: Optional[str], order: int) -> None:
        """The Go To step a loop edge becomes: the go_to record, ending its chain."""
        name = self._loop_goto_name(target_key)
        self.refs[nid] = name
        typ, attrs, extra = _goto_attrs(_strip_step(self.nodes[target_key].label))
        rec: Dict[str, Any] = {"type": typ, "id": nid, "name": name, "attributes": attrs, "order": order,
                               "parentKey": prev_id, "parentKeyName": prev_name}
        if branch_id:
            rec["parent"] = branch_id; rec["parentName"] = branch_name
        rec.update(extra)
        rec["next"] = ""
        self.gotos.append((rec, target_key, True))
        self.out.append(rec)

    def _resolve_gotos(self) -> None:
        for rec, target, from_loop in self.gotos:
            want = target.strip()
            hit = None
            if from_loop:
                hit = want if want in self.first_id else None
                if hit is None:
                    raise SpecError("loop back to {!r} from {!r}: that step is not in this workflow's "
                                    "chain, so there is nothing for a Go To to point at".format(
                                        want, rec.get("parentKeyName", "")))
            else:
                for k, n in self.nodes.items():
                    if k in self.first_id and (k == want or _strip_step(n.label) == _strip_step(want)
                                               or n.label == want):
                        hit = k; break
            if hit is None:
                self.unresolved.append("go_to:{} -> {}".format(rec["name"], target))
                continue
            rec["attributes"]["targetNodeId"] = self.first_id[hit]
            rec["attributes"]["targetNodeName"] = _strip_step(self.nodes[hit].label)
            self._check_goto_branch(rec, self.first_id[hit])

    def _branch_chain(self, rec: Dict[str, Any], by_id: Dict[str, Dict[str, Any]]) -> List[str]:
        """The If/Else branch ids `rec` sits inside, outermost first."""
        chain: List[str] = []
        cur = rec
        while cur.get("parent"):
            parent = by_id[cur["parent"]]
            if str(parent.get("nodeType", "")).startswith("branch-"):
                chain.append(parent["id"])
            cur = parent
        return chain[::-1]

    def _check_goto_branch(self, rec: Dict[str, Any], target_id: str) -> None:
        """Warn when a Go To points into an If/Else branch it is not inside
        (a sibling branch, or a branch entered from outside). UNVERIFIED
        whether GHL allows that: in the reference import the Go To's target
        was left at GHL's default (the first step), so no cross-branch pick
        has been tried yet."""
        by_id = {r["id"]: r for r in self.out}
        mine = self._branch_chain(rec, by_id)
        theirs = self._branch_chain(by_id[target_id], by_id)
        if mine[:len(theirs)] == theirs:
            return  # the target is on this Go To's own path (same branch or an outer level)
        branch = by_id[next(b for i, b in enumerate(theirs) if i >= len(mine) or mine[i] != b)]
        self._warn("Go To \"{}\" points at \"{}\", inside If/Else branch \"{}\" of \"{}\", which this Go To "
                   "is not in. GHL may not allow a Go To into another branch (unverified); check the "
                   "target after import".format(rec["name"], by_id[target_id]["name"], branch["name"],
                                                by_id[branch["parent"]]["name"]))

    def compile(self) -> Dict[str, Any]:
        s = self.spec
        triggers_spec = [n for n in self.nodes.values() if self._is_trigger(n.key)]
        if not triggers_spec:
            raise SpecError("GHL spec has no trigger")
        _check_triggers_lead_somewhere(triggers_spec, self.outgoing)
        starts: List[str] = []
        for t in triggers_spec:
            for dst, _b in self.outgoing.get(t.key, []):
                if dst not in starts:
                    starts.append(dst)
        if len(starts) != 1:
            raise SpecError("GHL workflow needs exactly one first action after the trigger(s); "
                            "got {}".format(", ".join(starts) or "none"))
        first = self._follow(starts[0])
        if first is None:
            raise SpecError("GHL workflow has no actions: the trigger goes straight to `end`")
        self.refs[self.workflow_id] = s.title
        now = _dt.datetime.now(_dt.timezone.utc).isoformat().replace("+00:00", "Z")
        triggers = []
        for t in triggers_spec:
            op = self.ops[t.key]
            tid = _short_id(); tname = _strip_step(t.label); self.refs[tid] = tname
            triggers.append({"id": tid, "date_added": now, "deleted": False, "active": False,
                             "actions": [{"workflow_id": self.workflow_id, "type": "add_to_workflow", "workflow_name": s.title}],
                             "conditions": self._trigger_conditions(t, op),
                             "type": TRIGGER_TYPES.get(op, op),
                             "masterType": "highlevel", "workflow_id": self.workflow_id,
                             "location_id": self.location_id, "name": tname, "belongs_to": "workflow",
                             "date_updated": now, "status": "draft", "workflow_name": s.title})
        self._emit(first, _uuid(), None, None, None, None, 0)
        self._resolve_gotos()
        return {
            "workflowId": self.workflow_id, "workflowName": s.title, "locationId": self.location_id,
            "url": "https://app.gohighlevel.com/v2/location/{}/automation/workflow/{}".format(self.location_id, self.workflow_id),
            "capturedAt": now, "status": "draft", "folder": None,
            "references": {"other": self.refs}, "unresolvedReferenceIds": [],
            "captureComplete": {"triggers": True, "tier": "compiled:upwork_gen"},
            "triggers": triggers,
            "metadata": {"createdAt": now, "updatedAt": now, "settings": {
                "locationId": self.location_id, "version": 1, "dataVersion": 7, "allowMultiple": True,
                "timezone": "account", "removeContactFromLastStep": True, "stopOnResponse": False,
                "autoMarkAsRead": False, "type": "workflow", "deleted": False, "allowMultipleOpportunity": True,
                "creationSource": "upwork_gen", "originType": "user"}},
            "nodes": self.out,
        }


# -- one workflow per independent trigger ---------------------------------------

def _check_triggers_lead_somewhere(triggers: List[Node],
                                   outgoing: Dict[str, List[Tuple[str, Optional[str]]]]) -> None:
    """A trigger with no (non-loop) edge out would otherwise read as a separate
    chain of its own, which is a misleading error."""
    for t in triggers:
        if not outgoing.get(t.key):
            raise SpecError("trigger {} ({!r}) has no next step; add an edge from it to the first "
                            "action".format(_strip_step(t.label), t.key))


def split_ghl_spec(spec: WorkflowSpec) -> List[Tuple[str, WorkflowSpec]]:
    """[(name_suffix, sub_spec)]. One entry ("", spec) unless the triggers start
    chains that share no step, in which case each trigger group gets its own
    sub-spec titled "<title> - <trigger label>"."""
    flow = [n for n in spec.nodes if not n.is_ai_sub]
    keys = {n.key for n in flow}
    ops = {n.key: _node_op(n) for n in flow}
    triggers = [n for n in flow if n.is_trigger or ops[n.key] in TRIGGER_OPS]
    flow_out: Dict[str, List[Tuple[str, Optional[str]]]] = {}
    for e in spec.edges:
        if not e.loop and e.dst in keys:
            flow_out.setdefault(e.src, []).append((e.dst, e.branch))
    _check_triggers_lead_somewhere(triggers, flow_out)
    if len(triggers) < 2:
        return [("", spec)]
    succ: Dict[str, List[str]] = {}
    for e in spec.edges:
        if e.src in keys and e.dst in keys:
            succ.setdefault(e.src, []).append(e.dst)
    trig_keys = {t.key for t in triggers}

    def reach(start: str) -> Set[str]:
        seen: Set[str] = set(); stack = list(succ.get(start, []))
        while stack:
            k = stack.pop()
            if k in seen or k in trig_keys:
                continue
            seen.add(k); stack.extend(succ.get(k, []))
        return seen

    groups: List[Tuple[List[str], Set[str]]] = []
    for t in triggers:
        r = reach(t.key)
        merged = ([t.key], set(r))
        rest = []
        for g in groups:
            if g[1] & merged[1]:
                merged = (g[0] + merged[0], g[1] | merged[1])
            else:
                rest.append(g)
        groups = rest + [merged]
    if len(groups) < 2:
        return [("", spec)]
    order = {t.key: i for i, t in enumerate(triggers)}
    groups.sort(key=lambda g: min(order[k] for k in g[0]))
    by_key = {n.key: n for n in flow}
    out: List[Tuple[str, WorkflowSpec]] = []
    for tkeys, body in groups:
        tkeys = sorted(tkeys, key=lambda k: order[k])
        members = set(tkeys) | body
        label = _strip_step(by_key[tkeys[0]].label)
        nodes = [n for n in spec.nodes if n.key in members or (n.is_ai_sub and n.parent in members)]
        edges = [Edge(src=e.src, dst=e.dst, branch=e.branch, loop=e.loop) for e in spec.edges
                 if e.src in members and e.dst in members]
        sections = [s for s in spec.sections if any(n.section == s.key for n in nodes)]
        sub = WorkflowSpec(title="{} - {}".format(spec.title, label), platform=spec.platform,
                           sections=sections, nodes=nodes, edges=edges,
                           input_sample=spec.input_sample, output_sample=spec.output_sample,
                           archetype=spec.archetype)
        out.append((label, sub))
    return out


def compile_ghl_many(spec: WorkflowSpec, ids: Optional[Dict[str, str]] = None,
                     location_id: str = "") -> List[Tuple[str, Dict[str, Any], List[str]]]:
    """[(name_suffix, workflow_json, unresolved)], one per independent trigger
    group. name_suffix is "" when the spec is a single workflow."""
    result: List[Tuple[str, Dict[str, Any], List[str]]] = []
    for suffix, sub in split_ghl_spec(spec):
        c = GHLCompiler(sub, ids, location_id)
        wf = c.compile()
        result.append((suffix, wf, sorted(set(c.unresolved))))
    return result


def compile_ghl(spec: WorkflowSpec, ids: Optional[Dict[str, str]] = None, location_id: str = "") -> Tuple[Dict[str, Any], List[str]]:
    parts = split_ghl_spec(spec)
    if len(parts) > 1:
        raise SpecError("spec has {} triggers that start separate chains; that is {} GHL workflows, "
                        "compile them with compile_ghl_many".format(len(parts), len(parts)))
    c = GHLCompiler(spec, ids, location_id)
    wf = c.compile()
    return wf, sorted(set(c.unresolved))


def main(argv: Optional[List[str]] = None) -> int:
    """python3 -m upwork_gen.compile_ghl <spec.json> <out.ghl.json>

    Compiles one single-workflow spec with the id map for UPWORK_GHL_LOCATION
    (default ebyNANPagaK7ycf1pfge), the same way generate.write_output does,
    and writes the file atomically. Ids and timestamps are fresh on every run.
    The text is generate.ascii_json: every string is folded to ASCII before
    serialising, so a curly quote in a label cannot end a JSON string early."""
    import argparse
    import json
    import os
    import sys
    import tempfile
    from .generate import ROOT, ascii_json

    ap = argparse.ArgumentParser(prog="python3 -m upwork_gen.compile_ghl")
    ap.add_argument("spec")
    ap.add_argument("out")
    args = ap.parse_args(argv)
    loc = os.environ.get("UPWORK_GHL_LOCATION", "ebyNANPagaK7ycf1pfge")
    ids_path = os.path.join(ROOT, "upwork_gen", "catalog", "ghl_ids_{}.json".format(loc))
    with open(ids_path, encoding="utf-8") as fh:
        ids = json.load(fh)
    with _warnings.catch_warnings(record=True) as caught:
        _warnings.simplefilter("always", GHLCompileWarning)
        wf, unresolved = compile_ghl(WorkflowSpec.load(args.spec), ids, loc)
    checks = [str(w.message) for w in caught if issubclass(w.category, GHLCompileWarning)]
    for w in caught:
        if not issubclass(w.category, GHLCompileWarning):
            _warnings.warn_explicit(w.message, w.category, w.filename, w.lineno)
    out = os.path.abspath(os.path.expanduser(args.out))
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(out), prefix=".ghl-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(ascii_json(wf))
        os.replace(tmp, out)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    print("wrote {} ({} steps, {} triggers)".format(out, len(wf["nodes"]), len(wf["triggers"])))
    if unresolved:
        print("unresolved (set by hand after import): " + "; ".join(unresolved), file=sys.stderr)
    for msg in checks:
        print("check after import: " + msg, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
