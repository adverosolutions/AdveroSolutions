"""WorkflowSpec -> Excalidraw DSL (for @swiftlysingh/excalidraw-cli).

The fourth compile target on the same spec. Excalidraw's CLI takes a DSL string
rather than JSON, so this emits the DSL and the CLI renders the `.excalidraw`
file — which means the diagram is generated from the identical graph the n8n
workflow is built from and cannot describe something different.

Two properties of the DSL drive the design:

* **Nodes are identified by their label text, not by an id.** Two nodes sharing
  a label silently become one node, joining flows that were never connected.
  Labels are de-duplicated before use, the same defence the n8n compiler needs
  for its `connections` object.
* **`[ ] { } ( )` are the shape delimiters**, so a label containing any of them
  breaks the parse. "Session Memory (10 turns)" is a parse error, not a node.
  Labels are sanitised rather than trusted.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

from .params import is_config_node
from .spec import AI_SUB_KINDS, TRIGGER_KINDS, Edge, Node, WorkflowSpec, unique_names

# Apps whose nodes read as storage rather than action — drawn as the DSL's
# database shape so the diagram distinguishes "does something" from "keeps
# something".
_STORE_APPS = {
    "postgres", "supabase", "googleSheets", "airtable", "notion",
    "googleDrive", "pinecone",
}

_STORE_KINDS = {"ai.vectorstore"}


def _clean(label: str) -> str:
    """Strip everything the DSL parser treats as syntax."""
    text = re.sub(r"[\[\]{}()]", "", str(label))
    text = text.replace('"', "'").replace("->", "to")
    text = re.sub(r"\s+", " ", text).strip()
    return text or "Step"


def _shape(node: Node, label: str, is_terminal: bool) -> str:
    if node.kind in TRIGGER_KINDS:
        return "({})".format(label)
    if node.kind in ("flow.branch", "flow.switch"):
        # The label is used verbatim, never dressed up with a question mark.
        # The diagram and the workflow are narrated back to back, so a node
        # whose caption differs between the two is a contradiction on camera.
        return "{{{}}}".format(label)
    if node.kind in _STORE_KINDS or (node.kind == "app.action" and node.app in _STORE_APPS):
        return "[[{}]]".format(label)
    return "[{}]".format(label)


def _bridge_config(spec: WorkflowSpec) -> List[Edge]:
    """The spec's edges with any Config node cut out: each edge into it is
    carried on to everything it fed, keeping that edge's branch and loop."""
    config = {n.key for n in spec.nodes if is_config_node(n)}
    if not config:
        return list(spec.edges)
    out: List[Edge] = []
    for edge in spec.edges:
        if edge.src in config:
            continue
        if edge.dst not in config:
            out.append(edge)
            continue
        frontier, seen = [edge.dst], set()
        while frontier:
            current = frontier.pop(0)
            if current in seen:
                continue
            seen.add(current)
            for onward in spec.edges:
                if onward.src != current:
                    continue
                if onward.dst in config:
                    frontier.append(onward.dst)
                elif not any(e.src == edge.src and e.dst == onward.dst for e in out):
                    out.append(Edge(src=edge.src, dst=onward.dst, branch=edge.branch,
                                    loop=edge.loop or onward.loop))
    return out


def compile_excalidraw(spec: WorkflowSpec, direction: str = "LR",
                       spacing: int = 60, include_ai: bool = True) -> str:
    """Render the spec as Excalidraw DSL.

    Left-to-right by default: a workflow reads as a pipeline, and a wide
    diagram fits a screen recording where a tall one forces scrolling.

    **The diagram is a faithful 1:1 of the workflow.** Every node on the n8n
    canvas appears here under the same label, and nothing appears here that is
    not on the canvas. The two get narrated back to back in one recording, so a
    node present in one and missing from the other is a visible contradiction —
    which outranks any argument about which nodes are interesting enough to
    draw. A test enforces the equivalence.
    """
    # The Config node is compiler plumbing, like the stickies: a spec that
    # carries one (a promoted archetype keeps the node the compiler inserted)
    # still draws without it, and the steps on either side join up.
    nodes = [n for n in (spec.nodes if include_ai else spec.flow_nodes)
             if not is_config_node(n)]
    edges = _bridge_config(spec)

    keys = {n.key for n in nodes}
    names = unique_names([(n.key, _clean(n.label)) for n in nodes])
    by_key: Dict[str, Node] = {n.key: n for n in nodes}

    terminals = [n.key for n in nodes if not any(e.src == n.key and not e.loop
                                                 for e in edges)]

    def token(key: str) -> str:
        node = by_key[key]
        return _shape(node, names[key], key in terminals)

    lines: List[str] = ["@direction {}".format(direction),
                        "@spacing {}".format(spacing), ""]

    for edge in edges:
        if edge.src not in keys or edge.dst not in keys:
            continue
        # A dashed arrow reads as a return path rather than another forward step.
        arrow = "-->" if edge.loop else "->"
        if edge.branch and not edge.loop:
            lines.append('{} -> "{}" -> {}'.format(
                token(edge.src), _clean(edge.branch), token(edge.dst)))
        else:
            lines.append("{} {} {}".format(token(edge.src), arrow, token(edge.dst)))

    # AI sub-nodes hang off their parent rather than sitting in the flow,
    # matching how n8n draws them on typed ports.
    for node in nodes:
        if node.kind in AI_SUB_KINDS and node.parent in keys:
            lines.append("{} --> {}".format(token(node.key), token(node.parent)))

    # No synthetic end state. A "(Done)" that exists only in the diagram is a
    # node the client can see and ask about, and the workflow has no answer.

    return "\n".join(lines) + "\n"


def excalidraw_command(spec: WorkflowSpec, out_path: str, dsl: Optional[str] = None) -> str:
    """The exact shell command that renders the DSL to a .excalidraw file."""
    body = dsl if dsl is not None else compile_excalidraw(spec)
    return (
        "npx @swiftlysingh/excalidraw-cli create --inline \"$(cat <<'EOF'\n"
        "{}"
        "EOF\n"
        ")\" -o {}".format(body, out_path)
    )


def _cli_args(dsl: str, out_path: str):
    return ["npx", "--yes", "@swiftlysingh/excalidraw-cli", "create",
            "--inline", dsl, "-o", out_path]


def render_async(dsl: str, out_path: str) -> bool:
    """Start the render and do not wait for it.

    Every run needs a scene, but the render is a slow npx step that has no
    business sitting in the generate path. Starting it here means it is
    usually finished by the time the workflow has been pasted and the diagram
    is asked for; `render` is still there to finish the job synchronously if
    it is not. Fire-and-forget — a failure here must never cost a generation.
    """
    import shutil
    import subprocess

    if shutil.which("npx") is None:
        return False
    try:
        subprocess.Popen(_cli_args(dsl, out_path),
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return False
    return True


def render(dsl: str, out_path: str, timeout: int = 180) -> Optional[str]:
    """Shell out to the Excalidraw CLI. Returns the path, or None on failure."""
    import shutil
    import subprocess

    if shutil.which("npx") is None:
        return None
    try:
        result = subprocess.run(
            _cli_args(dsl, out_path),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out_path if result.returncode == 0 else None
