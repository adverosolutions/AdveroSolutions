"""WorkflowSpec — the contract both generation engines write to.

The whole design rests on one rule: nothing outside this module ever names an
n8n node type or a Make module id. Engines emit a WorkflowSpec built from the
closed vocabulary below; the compilers translate it through a curated catalog.
That is what makes "imports first try" a property of the system rather than a
hope.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

# --------------------------------------------------------------------------
# Closed vocabulary. Adding a kind here means teaching both compilers about it,
# so the list is deliberately small and covers the shapes that actually show up
# in Upwork automation postings.
# --------------------------------------------------------------------------

TRIGGER_KINDS = {
    "trigger.webhook",
    "trigger.schedule",
    "trigger.email",
    "trigger.form",
    "trigger.chat",
    "trigger.app",
}

DATA_KINDS = {
    "data.transform",
    "data.code",
    "data.merge",
    "data.split",
    "data.aggregate",
    "data.filter",
}

FLOW_KINDS = {
    "flow.branch",
    "flow.switch",
    "flow.wait",
    "flow.noop",
}

# AI sub-nodes attach to a parent via a typed port instead of the main flow.
AI_PARENT_KINDS = {"ai.agent", "ai.llm"}
AI_SUB_KINDS = {
    "ai.model",
    "ai.memory",
    "ai.tool",
    "ai.embed",
    "ai.vectorstore",
    "ai.parser",
}
AI_KINDS = AI_PARENT_KINDS | AI_SUB_KINDS

APP_KINDS = {"app.action", "net.http", "net.respond"}

ALL_KINDS = TRIGGER_KINDS | DATA_KINDS | FLOW_KINDS | AI_KINDS | APP_KINDS

# Default port per AI sub-kind, so specs can omit `port` and still compile.
# Verified against a real n8n 2.32 export of an agent with every sub-node type.
DEFAULT_AI_PORT = {
    "ai.model": "ai_languageModel",
    "ai.memory": "ai_memory",
    "ai.tool": "ai_tool",
    "ai.embed": "ai_embedding",
    # A vector store attached to an agent is wired as a tool (retrieve-as-tool
    # mode), not on a vector-store port. `ai_vectorStore` is for the retriever
    # chain shape, which this generator does not emit.
    "ai.vectorstore": "ai_tool",
    "ai.parser": "ai_outputParser",
}

# Which kinds a given AI sub-node is allowed to hang off. Embeddings are the
# exception that matters: they attach to the *vector store*, not to the agent.
AI_PARENTS_FOR = {
    "ai.model": AI_PARENT_KINDS,
    "ai.memory": AI_PARENT_KINDS,
    "ai.tool": AI_PARENT_KINDS,
    "ai.parser": AI_PARENT_KINDS,
    "ai.vectorstore": AI_PARENT_KINDS,
    "ai.embed": AI_PARENT_KINDS | {"ai.vectorstore"},
}

# Kinds that fan out on more than one main output.
MULTI_OUTPUT_KINDS = {"flow.branch", "flow.switch", "data.split"}

# Platforms that can produce an importable file.
BUILDABLE_PLATFORMS = {"n8n", "make"}

# Platforms with no public import format. Zapier and GoHighLevel cannot accept
# a workflow file at all — you build in their UI or not at all — so for these
# the diagram IS the deliverable rather than an illustration of one. Saying so
# is also a better pitch than pretending otherwise: "there is no import format,
# so here is the architecture and I will build it live in your account."
DIAGRAM_ONLY_PLATFORMS = {"zapier", "gohighlevel", "diagram"}

PLATFORMS = BUILDABLE_PLATFORMS | DIAGRAM_ONLY_PLATFORMS


class SpecError(ValueError):
    """Raised when a spec cannot be trusted to compile into valid output."""


CLIENT_FIELDS = ("name", "company", "industry", "location")
OVERVIEW_FIELDS = ("how_it_works", "setup", "need_from_you")


def _clean_client(raw: Any) -> Dict[str, str]:
    """Keep the known client fields that carry text; ignore anything else."""
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, str] = {}
    for key in CLIENT_FIELDS:
        value = raw.get(key)
        if value is not None and str(value).strip():
            out[key] = str(value).strip()
    return out


def _clean_overview(raw: Any) -> Dict[str, List[str]]:
    """Each overview field is a list of bullet strings; a lone string is one bullet."""
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, List[str]] = {}
    for key in OVERVIEW_FIELDS:
        value = raw.get(key)
        if isinstance(value, str):
            value = [value]
        if isinstance(value, (list, tuple)):
            items = [str(v).strip() for v in value if v is not None and str(v).strip()]
            if items:
                out[key] = items
    return out


# A config key becomes `$('0 - Config: Your Settings').item.json.<key>` in
# every expression that reads it, so it must be a plain identifier.
CONFIG_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def config_key_fix(key: str) -> str:
    """The identifier a bad config key should be renamed to: "Booking Link"
    -> "booking_link"."""
    fixed = re.sub(r"[^a-z0-9]+", "_", str(key).lower()).strip("_")
    if not fixed or not fixed[0].isalpha():
        fixed = "setting_" + fixed
    return fixed


def _clean_config(raw: Any) -> Dict[str, Any]:
    """Setting name -> placeholder value. Keys are kept as written, in order."""
    if not isinstance(raw, dict):
        return {}
    return {str(k).strip(): v for k, v in raw.items() if str(k).strip()}


# --------------------------------------------------------------------------
# Data model
# --------------------------------------------------------------------------


@dataclass
class Section:
    """A labelled band of the canvas, rendered as a sticky note behind nodes.

    `color` of 0 means "let the layout pick" — the usual case. Specs normally
    omit it so the palette stays defined in one place rather than being
    re-chosen, and re-mistaken, per archetype.
    """

    key: str
    label: str
    color: int = 0
    note: str = ""

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Section":
        return Section(
            key=d["key"],
            label=d.get("label", d["key"]),
            color=int(d.get("color", 0)),
            note=d.get("note", ""),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "color": self.color,
            "note": self.note,
        }


# The Excalidraw DSL uses these as shape delimiters, so a label containing one
# cannot survive into the diagram. Normalising here — once, at parse time —
# means the n8n canvas and the diagram render the *same* string, instead of the
# diagram quietly dropping characters and the two captions disagreeing on
# camera. Fixing it in either compiler alone would only hide the divergence.
_LABEL_DELIMITERS = str.maketrans({"(": "·", ")": "", "[": "", "]": "",
                                   "{": "", "}": ""})


def normalise_label(label: str) -> str:
    text = str(label).translate(_LABEL_DELIMITERS)
    return re.sub(r"\s*·\s*", " · ", re.sub(r"\s+", " ", text)).strip()


@dataclass
class Node:
    key: str
    kind: str
    label: str
    app: Optional[str] = None
    op: Optional[str] = None
    section: Optional[str] = None
    # AI sub-nodes only: which node they hang off, and on which typed port.
    parent: Optional[str] = None
    port: Optional[str] = None
    # Free-form overrides merged over the catalog's default parameters.
    params: Dict[str, Any] = field(default_factory=dict)
    # Rendered as a caption under the node on the canvas. Cheap depth: it lets a
    # node say what it does without needing another node to say it.
    notes: Optional[str] = None

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Node":
        kind = d["kind"]
        port = d.get("port")
        if port is None and kind in AI_SUB_KINDS:
            port = DEFAULT_AI_PORT[kind]
        return Node(
            key=d["key"],
            kind=kind,
            label=normalise_label(d.get("label", d["key"])),
            app=d.get("app"),
            op=d.get("op"),
            section=d.get("section"),
            parent=d.get("parent"),
            port=port,
            params=d.get("params", {}) or {},
            notes=d.get("notes"),
        )

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"key": self.key, "kind": self.kind, "label": self.label}
        for name in ("app", "op", "section", "parent", "port", "notes"):
            value = getattr(self, name)
            if value:
                out[name] = value
        if self.params:
            out["params"] = self.params
        return out

    @property
    def is_trigger(self) -> bool:
        return self.kind in TRIGGER_KINDS

    @property
    def is_ai_sub(self) -> bool:
        return self.kind in AI_SUB_KINDS

    @property
    def catalog_key(self) -> str:
        """`kind:app:op` — how the compilers look this node up."""
        return "{}:{}:{}".format(self.kind, self.app or "", self.op or "")


@dataclass
class Edge:
    src: str
    dst: str
    # Label for the outgoing port on a branch/switch, e.g. "true" / "false".
    branch: Optional[str] = None
    # A back-edge, as in a batch loop returning to its splitter. Real n8n
    # workflows are full of these and they look authentic on canvas, but they
    # are cycles: layout ignores them while the compiler still wires them up.
    loop: bool = False

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Edge":
        # Accept both `from`/`to` (natural in hand-written JSON) and `src`/`dst`.
        src = d.get("from", d.get("src"))
        dst = d.get("to", d.get("dst"))
        if not src or not dst:
            raise SpecError("edge is missing 'from' or 'to': {!r}".format(d))
        return Edge(src=src, dst=dst, branch=d.get("branch"), loop=bool(d.get("loop", False)))

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"from": self.src, "to": self.dst}
        if self.branch:
            out["branch"] = self.branch
        if self.loop:
            out["loop"] = True
        return out


@dataclass
class WorkflowSpec:
    title: str
    platform: str = "n8n"
    sections: List[Section] = field(default_factory=list)
    nodes: List[Node] = field(default_factory=list)
    edges: List[Edge] = field(default_factory=list)
    input_sample: Dict[str, Any] = field(default_factory=dict)
    output_sample: Dict[str, Any] = field(default_factory=dict)
    # Archetype id when the spec came from the vault; None for LLM-authored.
    archetype: Optional[str] = None
    # Optional, all backward compatible. `client` names who the build is for
    # ({name, company, industry, location}); `overview` feeds the top-left
    # overview sticky ({how_it_works, setup, need_from_you}, each a list of
    # strings); `config` maps a setting name to a placeholder value and becomes
    # a "0 - Config: Your Settings" node right after the first trigger.
    client: Dict[str, str] = field(default_factory=dict)
    overview: Dict[str, List[str]] = field(default_factory=dict)
    config: Dict[str, Any] = field(default_factory=dict)

    # -- construction ------------------------------------------------------

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "WorkflowSpec":
        try:
            spec = WorkflowSpec(
                title=d["title"],
                platform=d.get("platform", "n8n"),
                sections=[Section.from_dict(s) for s in d.get("sections", [])],
                nodes=[Node.from_dict(n) for n in d.get("nodes", [])],
                edges=[Edge.from_dict(e) for e in d.get("edges", [])],
                input_sample=d.get("input_sample", {}) or {},
                output_sample=d.get("output_sample", {}) or {},
                archetype=d.get("archetype"),
                client=_clean_client(d.get("client")),
                overview=_clean_overview(d.get("overview")),
                config=_clean_config(d.get("config")),
            )
        except KeyError as exc:
            raise SpecError("spec is missing required field {}".format(exc)) from exc
        return spec

    @staticmethod
    def from_json(text: str) -> "WorkflowSpec":
        return WorkflowSpec.from_dict(json.loads(text))

    @staticmethod
    def load(path: str) -> "WorkflowSpec":
        with open(path, "r", encoding="utf-8") as fh:
            return WorkflowSpec.from_dict(json.load(fh))

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "title": self.title,
            "platform": self.platform,
            "sections": [s.to_dict() for s in self.sections],
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "input_sample": self.input_sample,
            "output_sample": self.output_sample,
        }
        if self.archetype:
            out["archetype"] = self.archetype
        if self.client:
            out["client"] = dict(self.client)
        if self.overview:
            out["overview"] = {k: list(v) for k, v in self.overview.items()}
        if self.config:
            out["config"] = dict(self.config)
        return out

    # -- lookups -----------------------------------------------------------

    def node(self, key: str) -> Node:
        for n in self.nodes:
            if n.key == key:
                return n
        raise SpecError("no node with key {!r}".format(key))

    @property
    def flow_nodes(self) -> List[Node]:
        """Nodes on the main graph — everything except AI sub-nodes."""
        return [n for n in self.nodes if not n.is_ai_sub]

    def children_of(self, key: str) -> List[Node]:
        return [n for n in self.nodes if n.parent == key]

    def successors(self, key: str, include_loops: bool = False) -> List[Edge]:
        """Outgoing edges. Back-edges are excluded unless asked for, because
        layout and ordering must see a DAG while compilation must see them all."""
        return [e for e in self.edges if e.src == key and (include_loops or not e.loop)]

    def predecessors(self, key: str, include_loops: bool = False) -> List[Edge]:
        return [e for e in self.edges if e.dst == key and (include_loops or not e.loop)]

    @property
    def flow_edges(self) -> List[Edge]:
        """Edges that define the left-to-right reading order."""
        return [e for e in self.edges if not e.loop]

    def entry_node(self) -> Node:
        """The node that carries `input_sample`.

        Prefer a declared trigger that is not an error trigger (the sample is
        the business payload, never an error report, even when the error
        trigger is declared first); fall back to the first flow node with no
        inbound edges, again skipping error triggers, so partial specs still
        compile.
        """
        for n in self.flow_nodes:
            if n.is_trigger and not is_error_trigger(n):
                return n
        for n in self.flow_nodes:
            if not self.predecessors(n.key) and not is_error_trigger(n):
                return n
        for n in self.flow_nodes:
            if not self.predecessors(n.key):
                return n
        if self.flow_nodes:
            return self.flow_nodes[0]
        raise SpecError("spec has no flow nodes")

    def exit_node(self) -> Node:
        """The node that carries `output_sample`.

        When several nodes are terminal (a branch that ends in two different
        actions), pick the one furthest from the trigger so the pinned output
        lands at the visual end of the canvas.
        """
        terminals = [n for n in self.flow_nodes if not self.successors(n.key)]
        if not terminals:
            return self.flow_nodes[-1]
        if len(terminals) == 1:
            return terminals[0]
        depths = self._depths()
        return max(terminals, key=lambda n: (depths.get(n.key, 0), n.key))

    def _depths(self) -> Dict[str, int]:
        """Longest-path depth per flow node. Also used by the layout engine."""
        order = self.topo_order()
        depth: Dict[str, int] = {n.key: 0 for n in self.flow_nodes}
        for key in order:
            for edge in self.successors(key):
                if edge.dst in depth:
                    depth[edge.dst] = max(depth[edge.dst], depth[key] + 1)
        return depth

    def topo_order(self) -> List[str]:
        """Kahn's algorithm over flow nodes. Raises on a cycle."""
        keys = [n.key for n in self.flow_nodes]
        keyset = set(keys)
        indeg = {k: 0 for k in keys}
        for e in self.flow_edges:
            if e.src in keyset and e.dst in keyset:
                indeg[e.dst] += 1
        # Seed in declaration order so layout is stable run to run.
        queue = [k for k in keys if indeg[k] == 0]
        order: List[str] = []
        while queue:
            key = queue.pop(0)
            order.append(key)
            for edge in self.successors(key):
                if edge.dst in indeg:
                    indeg[edge.dst] -= 1
                    if indeg[edge.dst] == 0:
                        queue.append(edge.dst)
        if len(order) != len(keys):
            stuck = sorted(set(keys) - set(order))
            raise SpecError(
                "workflow graph has a cycle involving: {}. If one of these edges is a "
                "deliberate loop-back (a batch loop returning to its splitter), mark it "
                '"loop": true so layout can ignore it while it still gets wired up.'.format(
                    ", ".join(stuck)
                )
            )
        return order

    # -- validation --------------------------------------------------------

    def validate(self) -> List[str]:
        """Raise on anything that would produce broken output; return warnings.

        Errors are things that make the compile invalid. Warnings are things
        that make it look worse than it should — worth surfacing, not worth
        blocking a generation on when the clock is running.
        """
        errors: List[str] = []
        warnings: List[str] = []

        if self.platform not in PLATFORMS:
            errors.append(
                "platform {!r} is not one of {}".format(self.platform, sorted(PLATFORMS))
            )

        if not self.nodes:
            errors.append("spec has no nodes")

        # Unique keys.
        seen: Set[str] = set()
        for n in self.nodes:
            if n.key in seen:
                errors.append("duplicate node key {!r}".format(n.key))
            seen.add(n.key)

        # Known kinds, and AI parent/port sanity.
        section_keys = {s.key for s in self.sections}
        for n in self.nodes:
            if n.kind not in ALL_KINDS:
                errors.append("node {!r} has unknown kind {!r}".format(n.key, n.kind))
            if n.kind == "app.action" and not n.app:
                errors.append("node {!r} is app.action but names no app".format(n.key))
            if n.is_ai_sub:
                if not n.parent:
                    errors.append("AI sub-node {!r} has no parent".format(n.key))
                elif n.parent not in seen:
                    errors.append(
                        "AI sub-node {!r} points at missing parent {!r}".format(n.key, n.parent)
                    )
                else:
                    allowed = AI_PARENTS_FOR.get(n.kind, AI_PARENT_KINDS)
                    parent_kind = self.node(n.parent).kind
                    if parent_kind not in allowed:
                        errors.append(
                            "AI sub-node {!r} ({}) hangs off {!r} ({}); allowed parents "
                            "are {}".format(
                                n.key, n.kind, n.parent, parent_kind, sorted(allowed)
                            )
                        )
            elif n.parent:
                errors.append(
                    "node {!r} sets parent but kind {!r} is not an AI sub-node".format(
                        n.key, n.kind
                    )
                )
            if n.section and n.section not in section_keys:
                warnings.append(
                    "node {!r} references undeclared section {!r}".format(n.key, n.section)
                )

        # Edges must connect real flow nodes.
        flow_keys = {n.key for n in self.flow_nodes}
        for e in self.edges:
            if e.src not in seen:
                errors.append("edge from missing node {!r}".format(e.src))
            elif e.src not in flow_keys:
                errors.append(
                    "edge from {!r}: AI sub-nodes connect via `parent`, not edges".format(e.src)
                )
            if e.dst not in seen:
                errors.append("edge to missing node {!r}".format(e.dst))
            elif e.dst not in flow_keys:
                errors.append(
                    "edge to {!r}: AI sub-nodes connect via `parent`, not edges".format(e.dst)
                )

        if errors:
            raise SpecError(
                "spec {!r} is not compilable:\n  - {}".format(self.title, "\n  - ".join(errors))
            )

        # Cycle check runs only once the graph is known to be well-formed.
        self.topo_order()

        # Quality warnings — these degrade the canvas without breaking it.
        triggers = [n for n in self.flow_nodes if n.is_trigger]
        if not triggers:
            warnings.append("no trigger node — the canvas will look like it starts mid-flow")
        elif len(triggers) > 1:
            warnings.append("{} trigger nodes; n8n renders these side by side".format(len(triggers)))

        for key in self.config:
            if not CONFIG_KEY_RE.match(key):
                warnings.append(
                    "config key {!r} is not a plain identifier (^[a-z][a-z0-9_]*$); rename it "
                    "to {!r}. Until then expressions read it with bracket notation.".format(
                        key, config_key_fix(key)))

        if not self.input_sample:
            warnings.append("input_sample is empty — the first node will have nothing pinned")
        if not self.output_sample:
            warnings.append("output_sample is empty — the last node will have nothing pinned")
        if not self.sections:
            warnings.append("no sections — the canvas will have no sticky-note labels")

        orphans = [
            n.key
            for n in self.flow_nodes
            if not n.is_trigger and not self.predecessors(n.key) and not self.successors(n.key)
        ]
        if orphans:
            warnings.append("disconnected nodes: {}".format(", ".join(orphans)))

        for n in self.flow_nodes:
            if n.kind in MULTI_OUTPUT_KINDS:
                labelled = [e for e in self.successors(n.key) if e.branch]
                if len(self.successors(n.key)) > 1 and not labelled:
                    warnings.append(
                        "node {!r} fans out but no edge names a branch".format(n.key)
                    )

        return warnings


ERROR_TRIGGER_OPS = frozenset({"error_trigger", "error_handler", "on_error"})
ERROR_TRIGGER_APPS = frozenset({"", "n8n", "make", "zapier"})
ERROR_TRIGGER_TYPE = "n8n-nodes-base.errorTrigger"


def declares_error_handler(node: Node) -> bool:
    """Whether an app trigger with no catalog node of its own asks to be a
    workflow error handler, decided by app and op only. The op is exactly
    error_trigger / error_handler / on_error, or the app is the automation
    platform itself (n8n, make, zapier, or none) and the op mentions error.
    A business event such as sentry/new_error or stripe/payment_error is not
    one, and neither is a label like "Recurring Payment Succeeded or Failed".
    params.trigger_stand_in uses it to pick Error Trigger over Webhook."""
    if not node.is_trigger:
        return False
    op = (node.op or "").strip().lower()
    if op in ERROR_TRIGGER_OPS:
        return True
    app = (node.app or "").strip().lower()
    return app in ERROR_TRIGGER_APPS and "error" in op


def is_error_trigger(node: Node, catalog: Any = None) -> bool:
    """A workflow error handler: True exactly when compile_n8n emits n8n's
    Error Trigger for this node. It asks the same resolution the compiler
    uses (the n8n catalog by kind, app and op, then
    params.trigger_stand_in), so it is decided by kind, app and op, never by
    label. That covers `trigger.app` with app n8n and any op (the catalog's
    app-level `trigger.app:n8n:` entry is the Error Trigger), and leaves out
    an app with a trigger of its own (calendly, facebook) whatever its op,
    and a webhook or schedule trigger."""
    if not node.is_trigger:
        return False
    from .params import n8n_entry
    return str(n8n_entry(node, catalog).get("type", "")) == ERROR_TRIGGER_TYPE


def slugify(text: str, max_len: int = 60) -> str:
    """Filename-safe slug for out/<slug>.json."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (slug[:max_len].rstrip("-")) or "workflow"


def unique_names(pairs: List[Tuple[str, str]]) -> Dict[str, str]:
    """Map node key -> display name, de-duplicating collisions.

    n8n keys its `connections` object off node *names*, so two nodes sharing a
    label would silently merge their connections. Suffix collisions instead.
    """
    used: Dict[str, int] = {}
    out: Dict[str, str] = {}
    for key, label in pairs:
        name = label.strip() or key
        if name in used:
            used[name] += 1
            name = "{} {}".format(name, used[name])
        else:
            used[name] = 1
        out[key] = name
    return out
