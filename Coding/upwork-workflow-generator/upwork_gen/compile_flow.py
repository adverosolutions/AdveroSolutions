"""WorkflowSpec -> Mermaid flowchart.

A third compile target beside n8n and Make, on the same spec. That is the whole
argument for keeping the flowchart inside this system rather than beside it: a
`WorkflowSpec` is already a platform-agnostic graph of labelled nodes, typed
edges and sections, which is exactly what a flowchart is. Building it separately
would mean a second classifier, a second vault, and — worse — a diagram and a
workflow that drift apart and describe different things in the same Loom.

Mermaid rather than SVG because it pastes into GitHub, Notion, and most docs
tools, renders natively in published Artifacts, and stays editable afterwards.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from .spec import AI_SUB_KINDS, TRIGGER_KINDS, Node, WorkflowSpec

# Shape per kind. A flowchart reader infers meaning from silhouette before
# reading a single label, so the mapping is worth getting right.
_SHAPES = {
    "trigger": ("([", "])"),      # stadium — an entry point
    "branch":  ("{", "}"),        # rhombus — a decision
    "ai":      ("{{", "}}"),      # hexagon — model work
    "store":   ("[(", ")]"),      # cylinder — persistence
    "default": ("[", "]"),
}

_SECTION_FILLS = ("#dbeafe", "#dcfce7", "#ede9fe", "#f1f5f9", "#fef9c3", "#ffedd5")


def _shape_for(node: Node) -> tuple:
    if node.kind in TRIGGER_KINDS:
        return _SHAPES["trigger"]
    if node.kind in ("flow.branch", "flow.switch"):
        return _SHAPES["branch"]
    if node.kind.startswith("ai."):
        return _SHAPES["ai"]
    if node.kind == "app.action" and node.app in ("postgres", "supabase", "googleSheets", "airtable"):
        return _SHAPES["store"]
    return _SHAPES["default"]


def _escape(text: str) -> str:
    """Mermaid label text. Quotes and brackets break the parser."""
    return (
        str(text)
        .replace('"', "'")
        .replace("[", "(")
        .replace("]", ")")
        .replace("\n", " ")
    )


def _label(node: Node) -> str:
    label = _escape(node.label)
    if node.app:
        label += "<br/><i>{}</i>".format(_escape(node.app))
    return label


def compile_flow(spec: WorkflowSpec, direction: str = "LR") -> str:
    """Render the spec as a Mermaid flowchart."""
    lines: List[str] = ["flowchart {}".format(direction)]
    by_key = {n.key: n for n in spec.nodes}

    def declare(node: Node, indent: str) -> str:
        open_shape, close_shape = _shape_for(node)
        return '{}{}{}"{}"{}'.format(indent, node.key, open_shape, _label(node), close_shape)

    # Sections become subgraphs. AI sub-nodes join whichever section their
    # parent belongs to, so a model stays visually attached to its agent.
    def section_of(node: Node) -> Optional[str]:
        seen = set()
        current: Optional[Node] = node
        while current is not None and current.key not in seen:
            if current.section:
                return current.section
            seen.add(current.key)
            current = by_key.get(current.parent) if current.parent else None
        return None

    placed = set()
    for index, section in enumerate(spec.sections):
        members = [n for n in spec.nodes if section_of(n) == section.key]
        if not members:
            continue
        lines.append('    subgraph sec_{}["{}"]'.format(section.key, _escape(section.label)))
        lines.append("        direction TB")
        for node in members:
            lines.append(declare(node, "        "))
            placed.add(node.key)
        lines.append("    end")

    for node in spec.nodes:
        if node.key not in placed:
            lines.append(declare(node, "    "))

    # Main flow. Loop-backs are drawn dotted so the eye reads them as a return
    # path rather than another forward step.
    for edge in spec.edges:
        if edge.loop:
            arrow = "-.->"
        else:
            arrow = "-->"
        if edge.branch:
            lines.append("    {} {}|{}| {}".format(
                edge.src, arrow, _escape(edge.branch), edge.dst))
        else:
            lines.append("    {} {} {}".format(edge.src, arrow, edge.dst))

    # AI sub-nodes attach with a dashed, unlabelled link — they are wiring, not
    # steps in the flow, and drawing them as steps misreads the diagram.
    for node in spec.nodes:
        if node.kind in AI_SUB_KINDS and node.parent:
            lines.append("    {} -.- {}".format(node.key, node.parent))

    for index, section in enumerate(spec.sections):
        fill = _SECTION_FILLS[index % len(_SECTION_FILLS)]
        lines.append("    style sec_{} fill:{},stroke:#94a3b8,color:#0f172a".format(
            section.key, fill))

    return "\n".join(lines) + "\n"


def compile_flow_markdown(spec: WorkflowSpec) -> str:
    """Fenced for pasting straight into GitHub, Notion, or an Artifact."""
    body = compile_flow(spec)
    notes = "\n".join(
        "- **{}** — {}".format(s.label, s.note) for s in spec.sections if s.note
    )
    return "# {}\n\n```mermaid\n{}```\n\n{}\n".format(spec.title, body, notes)
