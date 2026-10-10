"""WorkflowSpec -> n8n workflow JSON.

Notes on the parts that are easy to get subtly wrong:

* `connections` is keyed by node **name**, not id, so duplicate labels would
  silently merge two nodes' wiring. Names are de-duplicated before use.
* AI sub-nodes are the *source* of their connection: the model node owns an
  entry whose key is the port (`ai_languageModel`) pointing at the agent. They
  do not appear in the agent's `main` array.
* Node ids are derived deterministically from the workflow title and node key,
  so regenerating the same spec produces a byte-identical file. That keeps
  diffs readable when iterating on an archetype.
"""

from __future__ import annotations

import copy
import json
import re
import uuid
from typing import Any, Dict, List, Optional, Tuple

from .catalog import Catalog, get_catalog
from .layout import Placement, layout, section_content
from .params import (CONFIG_NODE_KEY, CONFIG_NODE_NAME, NODE_SETTINGS, compiles_to_http,
                     config_keys_read, config_keys_read_by, config_source,
                     distinct_set_params, enrich,
                     inline_unreached_config, is_config_node, is_error_trigger,
                     load_services, placeholder_value, resolve_service,
                     service_config_keys, strip_step, trigger_stand_in,
                     unreached_config_keys)
from .spec import Edge, MULTI_OUTPUT_KINDS, Node, SpecError, WorkflowSpec, unique_names

_NAMESPACE = uuid.UUID("6f3c1f4e-1f8d-4a2b-9c7e-0a5d2b6e4f11")

# Branch label -> main output index, per node kind. n8n renders an If node's
# first output as `true` and second as `false`; splitInBatches puts `done`
# first and `loop` second.
_BRANCH_INDEX = {
    "flow.branch": {"true": 0, "yes": 0, "false": 1, "no": 1},
    "data.split": {"done": 0, "loop": 1},
}


def _uid(*parts: str) -> str:
    return str(uuid.uuid5(_NAMESPACE, "::".join(parts)))


def _output_index(node: Node, branch: Optional[str], seen: List[str]) -> int:
    """Which `main` output a given edge leaves from."""
    label = (branch or "").strip().lower()
    table = _BRANCH_INDEX.get(node.kind)
    if table and label in table:
        return table[label]
    if node.kind not in MULTI_OUTPUT_KINDS:
        return 0
    # Switch and friends: outputs in the order their labels first appear.
    if label not in seen:
        seen.append(label)
    return seen.index(label)


def _apply_app_flavour(node: Node, entry: Dict[str, Any]) -> Dict[str, Any]:
    """A fallback HTTP node starts with an empty URL. params.for_http then
    resolves the real service endpoint, or leaves an obvious example.com
    placeholder; an invented `api.<app>.com` URL would look real and be wrong."""
    params = dict(entry.get("parameters", {}))
    if entry.get("type") == "n8n-nodes-base.httpRequest" and node.app:
        params.setdefault("url", "")
    return params


# --------------------------------------------------------------------------
# Config node
# --------------------------------------------------------------------------


def first_trigger(spec: WorkflowSpec) -> Optional[Node]:
    """The first declared trigger that is not an error trigger."""
    for node in spec.flow_nodes:
        if node.is_trigger and not is_error_trigger(node):
            return node
    return None


def _descendants(spec: WorkflowSpec, key: str) -> List[Node]:
    seen: List[str] = []
    frontier = [e.dst for e in spec.successors(key)]
    while frontier:
        current = frontier.pop(0)
        if current in seen:
            continue
        seen.append(current)
        frontier.extend(e.dst for e in spec.successors(current))
    out: List[Node] = []
    for k in seen:
        try:
            out.append(spec.node(k))
        except Exception:
            continue
    return out


def _join_point(spec: WorkflowSpec, triggers: List[Node]) -> Optional[Node]:
    """The first node every one of these triggers reaches: a common
    descendant with no other common descendant upstream of it."""
    reach = [{n.key for n in _descendants(spec, t.key)} for t in triggers]
    common = set.intersection(*reach) if reach else set()
    for node in spec.flow_nodes:
        if node.key in common and not any(a.key in common for a in
                                          _ancestors_of(spec, node.key)):
            return node
    return None


def _ancestors_of(spec: WorkflowSpec, key: str) -> List[Node]:
    seen: List[str] = []
    frontier = [e.src for e in spec.predecessors(key)]
    while frontier:
        current = frontier.pop(0)
        if current in seen:
            continue
        seen.append(current)
        frontier.extend(e.src for e in spec.predecessors(current))
    return [n for n in spec.flow_nodes if n.key in seen]


def _insert_after(out: WorkflowSpec, config: Node, anchor: Node) -> None:
    """anchor -> config -> everything anchor used to feed."""
    index = next(i for i, n in enumerate(out.nodes) if n.key == anchor.key)
    out.nodes.insert(index + 1, config)
    rewired: List[Edge] = [Edge(src=anchor.key, dst=config.key)]
    for edge in out.edges:
        if edge.src == anchor.key:
            rewired.append(Edge(src=config.key, dst=edge.dst, branch=edge.branch,
                                loop=edge.loop))
        else:
            rewired.append(edge)
    out.edges = rewired


def _insert_before(out: WorkflowSpec, config: Node, anchor: Node) -> None:
    """Everything that fed anchor -> config -> anchor. Loop-backs into the
    anchor stay where they are. Never used on a trigger."""
    index = next(i for i, n in enumerate(out.nodes) if n.key == anchor.key)
    out.nodes.insert(index, config)
    rewired: List[Edge] = [Edge(src=config.key, dst=anchor.key)]
    for edge in out.edges:
        if edge.dst == anchor.key and not edge.loop:
            rewired.append(Edge(src=edge.src, dst=config.key, branch=edge.branch))
        else:
            rewired.append(edge)
    out.edges = rewired


def _config_anchor(spec: WorkflowSpec) -> Optional[Tuple[Node, bool]]:
    """(anchor node, insert after it?) for the one Config node.

    * One business trigger: right after it.
    * Several business triggers that join: at the join, so everything after
      the join reads it. A Merge node gets it right after; any other join
      node gets it right in front (the paths still meet there first, and the
      join node itself can then read it).
    * Several business triggers that never join: after the first one.
    * Only an error trigger: after it. Never in front of any trigger.
    * No trigger at all: in front of the entry node.
    """
    business = [n for n in spec.flow_nodes if n.is_trigger and not is_error_trigger(n)]
    if len(business) > 1:
        join = _join_point(spec, business)
        if join is not None and not join.is_trigger:
            return join, join.kind == "data.merge"
    if business:
        return business[0], True
    triggers = [n for n in spec.flow_nodes if n.is_trigger]
    if triggers:
        return triggers[0], True
    try:
        entry = spec.entry_node()
    except SpecError:
        return None
    return entry, entry.is_trigger


def with_config_node(spec: WorkflowSpec) -> WorkflowSpec:
    """A copy of the spec with the one "0 - Config: Your Settings" node wired
    in, when the spec has a `config` block or its own node params read the
    Config node by name. Idempotent.

    There is exactly one Config node per workflow, placed by _config_anchor
    where it runs before the most nodes. An n8n expression can only read a
    node that ran earlier in the same execution, so only nodes the Config node
    dominates (every path into them passes through it) reference it;
    params.config_source decides that per node, and every other reader gets
    the literal PASTE-YOUR- value instead, including a by-name read the spec
    author wrote there (params.inline_unreached_config).

    The node carries every `config` key, then any key a param the spec author
    wrote on a node it runs before reads from it
    (`$('0 - Config: Your Settings').item.json.key`) that `config` does not
    list, as a PASTE-YOUR- placeholder, then any key an HTTP service it feeds
    needs (its API key, location id). The read keys matter for a vault
    archetype: promotion strips `config` but keeps those params.
    """
    read = config_keys_read(spec)
    if (not spec.config and read is None) or any(is_config_node(n) for n in spec.nodes):
        return spec
    found = _config_anchor(spec)
    if found is None:
        return spec
    anchor, after = found
    out = copy.deepcopy(spec)
    config = Node(key=CONFIG_NODE_KEY, kind="data.transform", label=CONFIG_NODE_NAME,
                  section=anchor.section,
                  notes="Every account id, list id and key this workflow uses, in one place.")
    if after:
        _insert_after(out, config, out.node(anchor.key))
    else:
        _insert_before(out, config, out.node(anchor.key))
    reachable = [n for n in out.nodes if config_source(n, out) is not None]
    # A key only a node off the Config node's path reads (the error alert's
    # address) is typed on that node instead (params.inline_unreached_config),
    # unless no node on the path reads any key at all.
    on_path = config_keys_read_by(reachable)
    for key in read or []:
        if key in on_path or not on_path:
            out.config.setdefault(key, placeholder_value(key))
    for key, value in service_config_keys(out, reachable).items():
        out.config.setdefault(key, value)
    return out


def config_node(spec: WorkflowSpec) -> Optional[Node]:
    for node in spec.nodes:
        if is_config_node(node):
            return node
    return None


# --------------------------------------------------------------------------
# Overview sticky
# --------------------------------------------------------------------------

_APP_NAMES = {
    "slack": "Slack", "googleSheets": "Google Sheets", "gmail": "Gmail",
    "airtable": "Airtable", "openai": "OpenAI", "anthropic": "Anthropic (Claude)",
    "hubspot": "HubSpot", "salesforce": "Salesforce", "notion": "Notion",
    "twilio": "Twilio", "googleCalendar": "Google Calendar", "googleDrive": "Google Drive",
    "googleDocs": "Google Docs", "telegram": "Telegram", "whatsapp": "WhatsApp",
    "discord": "Discord", "stripe": "Stripe", "shopify": "Shopify",
    "quickbooks": "QuickBooks", "postgres": "Postgres", "pinecone": "Pinecone",
    "supabase": "Supabase", "outlook": "Outlook", "microsoftOutlook": "Outlook",
    "wordpress": "WordPress", "ollama": "Ollama", "google": "Google Gemini",
    "gemini": "Google Gemini", "mistral": "Mistral", "groq": "Groq",
    "monday": "monday.com", "calendly": "Calendly",
}
_NO_CREDENTIAL_APPS = {"n8n", "http", "workflow", "html", "extractFile", "code", ""}
_DATABASE_APPS = {"Postgres", "Supabase", "Pinecone", "MySQL", "Mongo Db", "Redis"}

OVERVIEW_WORD_CAP = 300

# Hosts an explicit HTTP URL can target, for services that have no entry in
# http_services.json. Services that do have one are matched on their base_url.
_URL_HOSTS = {
    "api.hubapi.com": "HubSpot", "api.hubspot.com": "HubSpot",
    "api.airtable.com": "Airtable", "slack.com": "Slack", "hooks.slack.com": "Slack",
    "api.openai.com": "OpenAI", "api.anthropic.com": "Anthropic (Claude)",
    "graph.microsoft.com": "Microsoft 365", "api.stripe.com": "Stripe",
    "api.notion.com": "Notion", "api.twilio.com": "Twilio",
    "api.pipedrive.com": "Pipedrive", "api.trello.com": "Trello",
    "api.clickup.com": "ClickUp", "api.shopify.com": "Shopify",
    "sheets.googleapis.com": "Google Sheets", "www.googleapis.com": "Google",
    "api.telegram.org": "Telegram", "graph.facebook.com": "Meta (Facebook)",
    "api.zoom.us": "Zoom", "api.typeform.com": "Typeform",
}


_ACRONYMS = {"ai", "crm", "sms", "api", "ghl", "csv", "pdf", "url", "id", "qa", "kpi", "llm",
              "rag", "seo", "roi", "mls", "sop", "erp", "etl", "json", "b2b", "faq", "cta"}


def _vocabulary(spec: WorkflowSpec) -> Dict[str, str]:
    """Mixed-case spellings used anywhere in the spec ("GoHighLevel"), so an
    all-caps section label can be sentence-cased without mangling names."""
    vocab: Dict[str, str] = {}
    texts = [spec.title] + [n.label for n in spec.nodes] + [s.note for s in spec.sections]
    for text in texts:
        for word in re.findall(r"[A-Za-z][A-Za-z0-9.]*", text or ""):
            if not word.islower() and not word.isupper() and not word.istitle():
                vocab.setdefault(word.lower(), word)
    return vocab


def _sentence_case(text: str, vocab: Optional[Dict[str, str]] = None) -> str:
    text = strip_step(text).strip()
    if not text.isupper():
        return text
    vocab = vocab or {}
    out = []
    for word in (re.split(r"(\s+)", text.lower())):
        core = word.strip(",.;:!?()")
        if core in _ACRONYMS:
            word = word.replace(core, core.upper())
        elif core in vocab:
            word = word.replace(core, vocab[core])
        out.append(word)
    joined = "".join(out)
    return joined[:1].upper() + joined[1:]


def _split_sentences(text: str) -> List[str]:
    return [p for p in re.split(r"(?<=[.!?])\s+", (text or "").strip()) if p]


def _sentences(text: str, count: int = 1) -> str:
    """The first `count` whole sentences. Never cut inside a sentence."""
    return " ".join(_split_sentences(text)[:count])


def _app_name(app: str) -> str:
    if app in _APP_NAMES:
        return _APP_NAMES[app]
    spaced = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", app.replace("_", " "))
    return spaced[:1].upper() + spaced[1:]


def _url_service(node: Node) -> Optional[str]:
    """The service an explicit HTTP URL clearly targets, by host."""
    url = (node.params or {}).get("url")
    if not isinstance(url, str):
        return None
    match = re.search(r"https?://([A-Za-z0-9.-]+)", url)
    if not match:
        return None
    host = match.group(1).lower()
    for service in load_services().values():
        base = re.search(r"https?://([A-Za-z0-9.-]+)", str(service.get("base_url") or ""))
        if base and base.group(1).lower() == host:
            return str(service.get("name"))
    for known, name in _URL_HOSTS.items():
        if host == known or host.endswith("." + known):
            return name
    return None


def _credentials(spec: WorkflowSpec) -> List[Tuple[str, str, str]]:
    """(kind, display name, detail) per HTTP service and per app that needs a
    credential, once each, in canvas order. kind is "service" (a known API
    whose keys go in Config or on the HTTP node) or "app" (a credential
    connected on the node). An HTTP node with an explicit URL counts as the
    app its host belongs to."""
    out: List[Tuple[str, str, str]] = []
    seen: List[str] = []
    for node in spec.nodes:
        if is_config_node(node):
            continue
        found = resolve_service(node, spec)
        if found:
            key, service, _, _ = found
            name = service.get("name", key)
            if name in seen:
                continue
            seen.append(name)
            out.append(("service", name, service.get("setup", "API key")))
            continue
        name = None
        if node.kind in ("app.action", "ai.model", "ai.embed", "ai.vectorstore") or \
                (node.kind.startswith("trigger.") and node.app):
            app = node.app or ""
            if app not in _NO_CREDENTIAL_APPS:
                name = _app_name(app)
        if name is None and compiles_to_http(node):
            name = _url_service(node)
        if name and name not in seen:
            seen.append(name)
            out.append(("app", name, ""))
    return out


def _join(names: List[str]) -> str:
    if len(names) <= 1:
        return "".join(names)
    return "{} and {}".format(", ".join(names[:-1]), names[-1])


def _service_where(spec: WorkflowSpec, service_name: str) -> str:
    """Where a service's keys are entered: the Config node for the HTTP nodes
    it runs before, the PASTE-YOUR- values on the others."""
    nodes = []
    for node in spec.nodes:
        found = resolve_service(node, spec)
        if found and found[1].get("name", found[0]) == service_name:
            nodes.append(node)
    fed = [n for n in nodes if config_source(n, spec) is not None]
    if nodes and len(fed) == len(nodes):
        return "the {} node".format(CONFIG_NODE_NAME)
    if fed:
        return "the {} node, and replace the PASTE-YOUR- values on {}".format(
            CONFIG_NODE_NAME, _join(["'{}'".format(strip_step(n.label))
                                     for n in nodes if n not in fed]))
    return "its HTTP Request nodes (replace the PASTE-YOUR- values)"


def _trigger_setup(spec: WorkflowSpec) -> List[str]:
    bullets: List[str] = []
    for node in spec.flow_nodes:
        if not node.is_trigger:
            continue
        name = strip_step(node.label)
        if is_error_trigger(node):
            bullets.append("In the workflow settings, pick this workflow as its own Error "
                           "Workflow so '{}' fires on a failure.".format(name))
        elif node.kind == "trigger.webhook":
            bullets.append("Point the sender at the production URL of the '{}' "
                           "webhook.".format(name))
        elif node.kind == "trigger.schedule":
            bullets.append("Check the '{}' schedule runs in your timezone.".format(name))
        elif node.kind == "trigger.form":
            bullets.append("Share the production form URL from '{}'.".format(name))
        elif node.kind == "trigger.chat":
            bullets.append("Open the chat from '{}' and send a test message.".format(name))
        elif node.kind == "trigger.email":
            bullets.append("Connect the inbox '{}' watches.".format(name))
    return bullets


def default_setup(spec: WorkflowSpec) -> List[str]:
    """Config keys to fill in, each app once, each service's keys, what each
    trigger needs, and a test run. Never empty."""
    spec = with_config_node(spec)
    bullets: List[str] = []
    if config_node(spec) is not None:
        bullets.append("Fill in {} in the {} node.".format(_join(list(spec.config)),
                                                            CONFIG_NODE_NAME))
        # The error path and other trigger paths cannot read the Config node,
        # so the values a node there needs are typed on the node itself.
        for node, keys in unreached_config_keys(spec):
            if keys:
                bullets.append("Fill in {} on '{}', which runs without the Config "
                               "node.".format(_join(keys), strip_step(node.label)))
    creds = _credentials(spec)
    apps = [name for kind, name, _ in creds if kind == "app"]
    if apps:
        bullets.append("Connect your {} credential{} on {} node{}.".format(
            _join(apps), "s" if len(apps) > 1 else "", "their" if len(apps) > 1 else "its",
            "s" if len(apps) > 1 else ""))
    for kind, name, detail in creds:
        if kind == "service":
            bullets.append("{}: add your {} in {}.".format(name, detail,
                                                           _service_where(spec, name)))
    bullets.extend(_trigger_setup(spec))
    bullets.append("Run it once with the pinned sample data, then activate it.")
    return bullets


def default_need(spec: WorkflowSpec) -> List[str]:
    """What the client has to hand over, each app once. Never empty."""
    spec = with_config_node(spec)
    bullets: List[str] = []
    creds = _credentials(spec)
    apps = [name for kind, name, _ in creds if kind == "app" and name not in _DATABASE_APPS]
    if apps:
        bullets.append("Access to your {} account{}, or an invite.".format(
            _join(apps), "s" if len(apps) > 1 else ""))
    for kind, name, detail in creds:
        if kind == "service":
            bullets.append("Your {} {}.".format(name, detail))
        elif name in _DATABASE_APPS:
            bullets.append("Connection details for your {} database.".format(name))
    open_keys = [k for k, v in spec.config.items()
                 if not isinstance(v, str) or not v.strip() or "YOUR" in v.upper()]
    for _node, keys in unreached_config_keys(spec):
        for key in keys:
            value = spec.config.get(key, placeholder_value(key))
            if key not in open_keys and (not isinstance(value, str) or not value.strip()
                                         or "YOUR" in value.upper()):
                open_keys.append(key)
    if open_keys:
        bullets.append("The real values for {}.".format(_join(open_keys)))
    bullets.append("One real example of the incoming data to test with.")
    return bullets


def _render_overview(head: List[str], groups: List[Tuple[str, List[str]]]) -> str:
    lines = list(head)
    for heading, items in groups:
        lines.extend(["", "### {}".format(heading)])
        lines.extend("- {}".format(item) for item in items)
    return "\n".join(lines)


def overview_words(content: str) -> Tuple[int, int]:
    """(words, tokens): words carry a letter or digit; tokens are every
    whitespace-separated piece, markdown marks included."""
    tokens = content.split()
    return len([t for t in tokens if re.search(r"[A-Za-z0-9]", t)]), len(tokens)


def overview_markdown(spec: WorkflowSpec) -> str:
    """The top-left sticky: what this is, who it is for, how it works, setup,
    what I need from you.

    Built from real prose only: the spec's `overview` bullets, else each
    section's label and the first two sentences of its note, plus the
    generated setup and hand-over lists. There is no minimum length; a short
    overview is fine. Over 300 tokens, the longest list loses its last bullet
    first, then the longest bullet loses its last sentence; nothing is ever
    cut inside a sentence.
    """
    spec = with_config_node(spec)
    head = ["## {}".format(spec.title.strip())]
    who = spec.client.get("company") or spec.client.get("name")
    if who:
        head.extend(["", "Built for {}".format(who)])

    vocab = _vocabulary(spec)
    how = list(spec.overview.get("how_it_works") or [])
    if not how:
        for section in spec.sections:
            label = _sentence_case(section.label, vocab)
            sentence = _sentences(section.note, 2)
            how.append("{}: {}".format(label, sentence) if sentence else label)
    how = how or ["Runs {} end to end.".format(spec.title.strip())]
    setup = list(spec.overview.get("setup") or []) or default_setup(spec)
    need = list(spec.overview.get("need_from_you") or []) or default_need(spec)
    groups = [("How it works", how), ("Setup", setup), ("What I need from you", need)]

    def over() -> bool:
        return overview_words(_render_overview(head, groups))[1] > OVERVIEW_WORD_CAP

    # Whole bullets first: the longest list gives up its last bullet, and
    # every heading keeps at least one.
    while over():
        longest = max(groups, key=lambda g: len(g[1]))
        if len(longest[1]) <= 1:
            break
        longest[1].pop()
    # Then whole sentences off the longest multi-sentence bullet.
    while over():
        items = [(len(item.split()), gi, ii) for gi, (_, bullets) in enumerate(groups)
                 for ii, item in enumerate(bullets) if len(_split_sentences(item)) > 1]
        if not items:
            break
        _, gi, ii = max(items)
        groups[gi][1][ii] = " ".join(_split_sentences(groups[gi][1][ii])[:-1])
    return _render_overview(head, groups)


def compile_n8n(spec: WorkflowSpec, catalog: Optional[Catalog] = None) -> Dict[str, Any]:
    catalog = catalog or get_catalog("n8n", fresh=True)
    # Samples pin on the spec's own first and last nodes, never on an
    # inserted Config node (which can be the first node of a trigger-less spec).
    entry_key = spec.entry_node().key
    exit_key = spec.exit_node().key
    spec = with_config_node(spec)
    overview = overview_markdown(spec)
    placement = layout(spec, overview=overview)
    names = unique_names([(n.key, n.label) for n in spec.nodes])

    nodes: List[Dict[str, Any]] = []
    # Field-name lists of the Set nodes emitted so far; no two may match.
    set_fields: List[Tuple[str, ...]] = []

    if placement.overview is not None:
        o = placement.overview
        nodes.append(
            {
                "parameters": {
                    "content": o.content,
                    "height": o.height,
                    "width": o.width,
                    "color": o.color,
                },
                "id": _uid(spec.title, "sticky", "__overview"),
                "name": "Overview",
                "type": (catalog.sticky or {}).get("type", "n8n-nodes-base.stickyNote"),
                "typeVersion": (catalog.sticky or {}).get("typeVersion", 1),
                "position": [o.x, o.y],
            }
        )

    # Sticky notes first so they render behind everything else.
    sticky_meta = catalog.sticky or {}
    sticky_type = sticky_meta.get("type", "n8n-nodes-base.stickyNote")
    sticky_version = sticky_meta.get("typeVersion", 1)
    for sticky in placement.stickies:
        content = sticky.content or section_content(sticky.label, sticky.note)
        nodes.append(
            {
                "parameters": {
                    "content": content,
                    "height": sticky.height,
                    "width": sticky.width,
                    "color": sticky.color,
                },
                "id": _uid(spec.title, "sticky", sticky.key),
                "name": "Section — {}".format(sticky.label),
                "type": sticky_type,
                "typeVersion": sticky_version,
                "position": [sticky.x, sticky.y],
            }
        )

    for node in spec.nodes:
        if node.key not in placement.positions:
            continue
        resolution = catalog.resolve(node)
        entry = resolution.entry
        # An app trigger with no catalog entry of its own never borrows
        # another app's trigger (Calendly); see params.trigger_stand_in.
        stand_in = trigger_stand_in(node, catalog)
        if stand_in and catalog.entries.get(stand_in):
            entry = copy.deepcopy(catalog.entries[stand_in])
            catalog.fallback_used.append("{} ({})".format(node.label, node.catalog_key))
        params = _apply_app_flavour(node, entry)
        # Synthesised config comes next, then the spec's raw params win.
        # Shorthand keys in node.params are translated and stripped inside
        # enrich(), so only real n8n parameters reach the file. An empty node
        # undercuts the label above it — a workflow that promises routing and
        # shows nothing when clicked reads as a mock-up.
        params = enrich(node, spec, params)
        # A by-name Config read the spec author wrote on a path the Config node
        # never runs on (the error path, another trigger) gets the value itself.
        params = inline_unreached_config(node, spec, params)
        if entry["type"] == "n8n-nodes-base.set" and not is_config_node(node):
            fields = tuple(a.get("name") for a in (params.get("assignments") or {})
                           .get("assignments", []))
            authored = "assignments" in (node.params or {})
            if fields in set_fields:
                # A synthesised list is replaced; an authored one keeps every
                # field it wrote (a chat reply's `output`) and gains the step
                # stamp after them.
                keep = params["assignments"]["assignments"] if authored else None
                distinct = distinct_set_params(node, spec, set(set_fields), keep=keep)
                if authored:
                    params["assignments"] = dict(params["assignments"],
                                                 assignments=distinct["assignments"]
                                                 ["assignments"])
                else:
                    params.update(distinct)
                fields = tuple(a.get("name") for a in params["assignments"]["assignments"])
            set_fields.append(fields)
        settings = {k: params.pop(k) for k in NODE_SETTINGS if k in params}

        x, y = placement.positions[node.key]
        payload: Dict[str, Any] = {
            "parameters": params,
            "id": _uid(spec.title, node.key),
            "name": names[node.key],
            "type": entry["type"],
            "typeVersion": entry.get("typeVersion", 1),
            "position": [x, y],
        }
        # Retry and error settings live on the node, not in its parameters.
        payload.update(settings)
        if node.notes:
            payload["notes"] = node.notes
            payload["notesInFlow"] = True
        if entry["type"] == "n8n-nodes-base.webhook":
            payload["webhookId"] = _uid(spec.title, node.key, "webhook")
        nodes.append(payload)

    # -- connections -------------------------------------------------------
    connections: Dict[str, Dict[str, List[List[Dict[str, Any]]]]] = {}

    for node in spec.flow_nodes:
        # Loop-backs are wired here even though layout ignored them — that is
        # what makes a batch loop actually look like a loop on the canvas.
        edges = spec.successors(node.key, include_loops=True)
        if not edges:
            continue
        seen_labels: List[str] = []
        buckets: Dict[int, List[Dict[str, Any]]] = {}
        for edge in edges:
            index = _output_index(node, edge.branch, seen_labels)
            buckets.setdefault(index, []).append(
                {"node": names[edge.dst], "type": "main", "index": 0}
            )
        width = max(buckets) + 1
        connections[names[node.key]] = {
            "main": [buckets.get(i, []) for i in range(width)]
        }

    # AI sub-nodes own their connection into the parent, keyed by port.
    for node in spec.nodes:
        if not node.is_ai_sub or not node.parent:
            continue
        port = node.port or "ai_languageModel"
        connections.setdefault(names[node.key], {})[port] = [
            [{"node": names[node.parent], "type": port, "index": 0}]
        ]

    # -- pinned sample data on the first and last node ---------------------
    pin_data: Dict[str, List[Dict[str, Any]]] = {}
    if spec.input_sample:
        pin_data[names[entry_key]] = _as_items(spec.input_sample)
    if spec.output_sample and exit_key != entry_key:
        pin_data[names[exit_key]] = _as_items(spec.output_sample)

    workflow: Dict[str, Any] = {
        "name": spec.title,
        "nodes": nodes,
        "connections": connections,
        "active": False,
        "settings": {"executionOrder": "v1"},
        "tags": [],
        "meta": {"templateCredsSetupCompleted": True},
        "versionId": _uid(spec.title, "version"),
    }
    if pin_data:
        workflow["pinData"] = pin_data
    return workflow


def _as_items(sample: Any) -> List[Dict[str, Any]]:
    """n8n pins a list of items; accept either a dict or a list of dicts."""
    if isinstance(sample, list):
        return [{"json": item} for item in sample]
    return [{"json": sample}]


def to_json(spec: WorkflowSpec, catalog: Optional[Catalog] = None) -> str:
    return json.dumps(compile_n8n(spec, catalog), indent=2, ensure_ascii=False)
