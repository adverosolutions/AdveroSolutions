"""Deterministic canvas layout.

This module is the reason generated workflows look designed rather than dumped.
No model places anything; placement is a pure function of the graph, so the
canvas is tidy on every single generation instead of most of them.

Three ideas do the work:

* **Longest-path columns.** A node sits one column right of its deepest
  predecessor, so flow reads strictly left to right with no back-edges.
* **Section-aware gaps.** Columns get extra horizontal clearance wherever the
  section changes. That separation is what lets sticky notes wrap each stage
  without ever overlapping each other.
* **Reserved AI bands.** An agent with sub-nodes claims vertical space below
  itself during row assignment, so the language model and memory nodes never
  land on top of something else.
"""

from __future__ import annotations

import math
import textwrap
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .spec import MULTI_OUTPUT_KINDS, Node, WorkflowSpec

# Canvas geometry. n8n snaps to a 20px grid; everything here is a multiple.
GRID = 20

# n8n does not render one node size, it renders two. Ordinary nodes are a ~100px
# square; agent and chain nodes draw as a wide card roughly twice that. Sizing
# everything the same made wide nodes overflow their section band and crowd the
# column to their right.
NODE_W_STD = 100
NODE_W_WIDE = 200
WIDE_KINDS = {"ai.agent", "ai.llm"}

NODE_H = 100            # the icon box itself
LABEL_H = 60            # name and subtitle render *below* the box
AI_NODE_H = 100

H_GAP = 140             # clear space between one column's right edge and the next
ROW_STEP = 180          # vertical distance between stacked nodes in a column
SECTION_GAP = 140       # extra horizontal clearance across a section boundary

AI_DROP = 220           # how far below a parent its sub-nodes sit
AI_STEP = 200           # horizontal spacing between sibling sub-nodes

STICKY_PAD_X = 60
STICKY_PAD_TOP = 110    # minimum room for the sticky's heading above the first node
STICKY_PAD_BOTTOM = 70
HEADING_CLEARANCE = 30  # gap between the last line of sticky text and the first node

# A one-column section is only ~220px wide, which wraps its note into a tall
# ribbon of text. Narrow stickies are widened into the free gap beside them,
# never closer than STICKY_MIN_GAP to a neighbour.
STICKY_MIN_W = 360
STICKY_MIN_GAP = 40

# The overview sticky sits left of everything, top-aligned with the bands.
OVERVIEW_W = 520
OVERVIEW_GAP = 100
OVERVIEW_COLOR = 1      # yellow: n8n's default sticky colour

# Text metrics for estimating how tall a sticky's markdown renders. Deliberately
# generous: a heading that runs into a node is worse than a little air.
_TEXT_PAD = 20
_METRICS = {            # (average char width px, line height px, extra spacing px)
    "h2": (12.0, 30, 10),
    "h3": (10.0, 24, 8),
    "body": (7.4, 21, 0),
}


def section_content(label: str, note: str) -> str:
    """The markdown a section sticky shows. Shared with the compiler so the
    height estimated here is the height of the text actually rendered."""
    content = "## {}".format(label)
    if note:
        content += "\n\n{}".format(note)
    return content


def text_height(content: str, width: int) -> int:
    """Estimated rendered height of sticky markdown at a given sticky width."""
    inner = max(80, width - 2 * _TEXT_PAD)
    height = _TEXT_PAD
    for raw in content.split("\n"):
        line = raw.strip()
        if not line:
            height += 8
            continue
        if line.startswith("### "):
            style, line = "h3", line[4:]
        elif line.startswith("## ") or line.startswith("# "):
            style, line = "h2", line.split(" ", 1)[1]
        else:
            style = "body"
        char_w, line_h, extra = _METRICS[style]
        per_line = max(6, int(inner / char_w))
        count = len(textwrap.wrap(line, per_line)) or 1
        height += count * line_h + extra
    return int(height)


def _snap_up(value: float) -> int:
    return int(math.ceil(value / float(GRID)) * GRID)

# Verified from a real canvas: 3=red, 4=green, 5=blue, 6=purple, 7=grey.
# Red is deliberately not in the rotation — it reads as an error state, which is
# wrong for a section that is merely doing the work. 1 is n8n's default yellow
# and is kept for the overview sticky alone, so no section band shares its
# colour. 2 remains unconfirmed.
SECTION_COLORS = (5, 4, 6, 7, 2)


def snap(value: float) -> int:
    return int(round(value / GRID) * GRID)


def node_width(node: Optional[Node]) -> int:
    if node is not None and node.kind in WIDE_KINDS:
        return NODE_W_WIDE
    return NODE_W_STD


def node_height(node: Optional[Node]) -> int:
    """Icon box plus the label beneath it — the label is part of what a section
    band has to enclose, or the caption spills outside the sticky."""
    if node is not None and node.is_ai_sub:
        return AI_NODE_H + LABEL_H
    return NODE_H + LABEL_H


def _effective_section(node: Node, by_key: Dict[str, Node]) -> Optional[str]:
    """The section a node belongs to, following `parent` up for sub-nodes."""
    seen = set()
    current: Optional[Node] = node
    while current is not None and current.key not in seen:
        if current.section:
            return current.section
        seen.add(current.key)
        current = by_key.get(current.parent) if current.parent else None
    return None


def _separate_sections(spec: WorkflowSpec, depth: Dict[str, int], order: List[str]) -> None:
    """Give each section an exclusive range of columns, in place.

    Without this, a branch whose two arms belong to different sections puts
    both sections in the same column, and their sticky notes end up drawn on
    top of each other. Sections are pushed rightward — never leftward — in the
    order the author declared them, then edges are repaired so every one still
    points right. Depths only ever increase, so the pass terminates.
    """
    sections = [s.key for s in spec.sections]
    if len(sections) < 2:
        return

    members: Dict[str, List[str]] = {}
    for node in spec.flow_nodes:
        if node.section:
            members.setdefault(node.section, []).append(node.key)

    for _ in range(6):
        moved = False

        required = 0
        for key in sections:
            group = members.get(key)
            if not group:
                continue
            lowest = min(depth[k] for k in group)
            if lowest < required:
                shift = required - lowest
                for node_key in group:
                    depth[node_key] += shift
                moved = True
            required = max(depth[k] for k in group) + 1

        # Repair any edge the shift just pushed backwards.
        for _pass in range(len(order) + 1):
            broke = False
            for edge in spec.flow_edges:
                if edge.src in depth and edge.dst in depth:
                    if depth[edge.dst] <= depth[edge.src]:
                        depth[edge.dst] = depth[edge.src] + 1
                        broke = True
                        moved = True
            if not broke:
                break

        if not moved:
            return


@dataclass
class StickyRect:
    key: str
    label: str
    note: str
    color: int
    x: int
    y: int
    width: int
    height: int
    # Estimated height of the rendered text, measured from the sticky's top.
    heading: int = 0
    content: str = ""


@dataclass
class Placement:
    positions: Dict[str, Tuple[int, int]] = field(default_factory=dict)
    stickies: List[StickyRect] = field(default_factory=list)
    columns: Dict[str, int] = field(default_factory=dict)
    # The top-left overview sticky, when the compiler asked for one.
    overview: Optional[StickyRect] = None

    def bbox(self, key: str, node: Optional[Node] = None) -> Tuple[int, int, int, int]:
        x, y = self.positions[key]
        return (x, y, x + node_width(node), y + node_height(node))


def layout(spec: WorkflowSpec, overview: Optional[str] = None) -> Placement:
    """Place every node and sticky. `overview` is the markdown of the overview
    sticky; when given, it is sized to its text and parked left of the canvas."""
    flow = spec.flow_nodes
    if not flow:
        return Placement()

    order = spec.topo_order()
    index_of = {n.key: i for i, n in enumerate(flow)}
    by_key = {n.key: n for n in spec.nodes}

    # -- 1. columns from longest-path depth ---------------------------------
    depth: Dict[str, int] = {n.key: 0 for n in flow}
    for key in order:
        for edge in spec.successors(key):
            if edge.dst in depth:
                depth[edge.dst] = max(depth[edge.dst], depth[key] + 1)

    _separate_sections(spec, depth, order)

    columns: Dict[int, List[str]] = {}
    for key in order:
        columns.setdefault(depth[key], []).append(key)

    # -- 2. x per column, with extra clearance across section boundaries ----
    # A column's section is the one most of its nodes belong to.
    col_section: Dict[int, Optional[str]] = {}
    for col, keys in columns.items():
        tally: Dict[Optional[str], int] = {}
        for key in keys:
            section = by_key[key].section
            tally[section] = tally.get(section, 0) + 1
        col_section[col] = max(tally.items(), key=lambda kv: (kv[1], str(kv[0])))[0]

    # An agent's sub-nodes fan out horizontally under it, so a column holding
    # one is wider than a node. Without accounting for that overhang the
    # cluster reaches into the neighbouring column and drags its section's
    # sticky note over the one next door.
    overhang: Dict[int, float] = {}
    for col, keys in columns.items():
        widest = 0.0
        for key in keys:
            children = spec.children_of(key)
            if len(children) > 1:
                widest = max(widest, (len(children) - 1) * AI_STEP / 2.0)
        overhang[col] = widest

    # Column pitch follows the widest node actually in that column, so a column
    # holding a wide agent card gets the room it needs and a column of ordinary
    # nodes does not get padded out for nothing.
    col_width: Dict[int, int] = {}
    for col, keys in columns.items():
        col_width[col] = max(node_width(by_key[k]) for k in keys)

    col_x: Dict[int, int] = {}
    cursor = 0
    previous_section = None
    previous_col = None
    for col in sorted(columns):
        if previous_col is not None:
            cursor += col_width[previous_col] + H_GAP
            cursor += overhang[previous_col] + overhang[col]
            if col_section[col] != previous_section:
                cursor += SECTION_GAP
        col_x[col] = int(cursor)
        previous_section = col_section[col]
        previous_col = col

    # -- 3. y per node, honouring preferred position and reserved AI space --
    positions: Dict[str, Tuple[int, int]] = {}
    y_of: Dict[str, float] = {}

    def reserved_height(key: str) -> float:
        """A node's vertical footprint, including any docked AI sub-nodes."""
        if spec.children_of(key):
            return AI_DROP + node_height(by_key.get(key))
        return node_height(by_key.get(key))

    for col in sorted(columns):
        keys = columns[col]
        preferred: Dict[str, float] = {}
        for key in keys:
            parents = [e.src for e in spec.predecessors(key) if e.src in y_of]
            if not parents:
                preferred[key] = 0.0
                continue
            # Fan children out symmetrically around a branching parent so an
            # If node reads as a genuine split rather than a lopsided drop.
            anchor = parents[0]
            siblings = [e.dst for e in spec.successors(anchor)]
            parent_node = by_key[anchor]
            if len(siblings) > 1 and parent_node.kind in MULTI_OUTPUT_KINDS:
                position = siblings.index(key)
                offset = (position - (len(siblings) - 1) / 2.0) * ROW_STEP
                preferred[key] = y_of[anchor] + offset
            else:
                preferred[key] = sum(y_of[p] for p in parents) / float(len(parents))

        ordered = sorted(keys, key=lambda k: (preferred[k], index_of[k]))
        cursor_y = None
        for key in ordered:
            want = preferred[key]
            y = want if cursor_y is None else max(want, cursor_y)
            y_of[key] = y
            cursor_y = y + reserved_height(key) + (ROW_STEP - NODE_H)

    # Normalise so the canvas starts near the origin.
    min_y = min(y_of.values())
    for key, y in y_of.items():
        positions[key] = (snap(col_x[depth[key]]), snap(y - min_y))

    # -- 4. AI sub-nodes dock below their parent ----------------------------
    # Level by level, because sub-nodes can themselves have sub-nodes: an
    # embeddings node hangs off the vector store, not off the agent.
    frontier = [n.key for n in flow]
    for _level in range(4):
        next_frontier: List[str] = []
        for parent_key in frontier:
            children = spec.children_of(parent_key)
            if not children or parent_key not in positions:
                continue
            px, py = positions[parent_key]
            span = (len(children) - 1) * AI_STEP
            # Centre the cluster on the parent's centre, not its left edge —
            # a wide agent card is twice the width of the sub-nodes under it.
            parent_centre = px + node_width(by_key.get(parent_key)) / 2.0
            start_x = parent_centre - (span / 2.0) - (NODE_W_STD / 2.0)
            for i, child in enumerate(children):
                positions[child.key] = (snap(start_x + i * AI_STEP), snap(py + AI_DROP))
                next_frontier.append(child.key)
        if not next_frontier:
            break
        frontier = next_frontier

    # -- 5. sticky rects wrapping each section ------------------------------
    stickies: List[StickyRect] = []
    bounds: Dict[str, Tuple[int, int, int, int]] = {}
    for i, section in enumerate(spec.sections):
        # An AI sub-node inherits its section from whatever it ultimately hangs
        # off, so a model, a vector store and that store's embeddings all stay
        # inside the band with the agent they serve.
        members = [
            n for n in spec.nodes
            if n.key in positions and _effective_section(n, by_key) == section.key
        ]
        if not members:
            continue

        x0 = min(positions[n.key][0] for n in members)
        y0 = min(positions[n.key][1] for n in members)
        x1 = max(positions[n.key][0] + node_width(n) for n in members)
        y1 = max(positions[n.key][1] + node_height(n) for n in members)
        bounds[section.key] = (x0, y0, x1, y1)

        color = section.color if section.color else SECTION_COLORS[i % len(SECTION_COLORS)]
        stickies.append(
            StickyRect(
                key=section.key,
                label=section.label,
                note=section.note,
                color=color,
                x=snap(x0 - STICKY_PAD_X),
                y=0,
                width=snap((x1 - x0) + 2 * STICKY_PAD_X),
                height=0,
                content=section_content(section.label, section.note),
            )
        )

    _widen_narrow(stickies, spec, positions, by_key)

    # Height grows with the note: the heading area is whatever the text needs
    # at this sticky's width, so a long note never runs into the first node.
    for sticky in stickies:
        x0, y0, x1, y1 = bounds[sticky.key]
        sticky.heading = text_height(sticky.content, sticky.width)
        pad_top = max(STICKY_PAD_TOP, _snap_up(sticky.heading + HEADING_CLEARANCE))
        sticky.y = snap(y0) - pad_top
        sticky.height = snap(y1 - y0) + pad_top + STICKY_PAD_BOTTOM

    # Square the bands off to a shared top and height. Ragged sticky edges are
    # the single clearest tell that a canvas was generated rather than laid out
    # by hand; uniform bands read as deliberate swimlanes.
    if stickies:
        top = min(s.y for s in stickies)
        bottom = max(s.y + s.height for s in stickies)
        for sticky in stickies:
            sticky.y = top
            sticky.height = bottom - top

    overview_rect = None
    if overview:
        overview_rect = _place_overview(overview, stickies, positions, by_key)

    return Placement(positions=positions, stickies=stickies, columns=dict(depth),
                     overview=overview_rect)


def _widen_narrow(stickies: List[StickyRect], spec: WorkflowSpec,
                  positions: Dict[str, Tuple[int, int]], by_key: Dict[str, Node]) -> None:
    """Widen stickies narrower than STICKY_MIN_W into the free space beside
    them. Neighbouring stickies split a shared gap; other sections' nodes are
    hard limits. Every band is treated as full height, since they are squared
    off afterwards."""
    originals = [(s.key, s.x, s.x + s.width) for s in stickies]
    for sticky in stickies:
        need = STICKY_MIN_W - sticky.width
        if need <= 0:
            continue
        left_room = float("inf")
        right_room = float("inf")
        for key, ox0, ox1 in originals:
            if key == sticky.key:
                continue
            if ox1 <= sticky.x:
                left_room = min(left_room, (sticky.x - ox1 - STICKY_MIN_GAP) / 2.0)
            elif ox0 >= sticky.x + sticky.width:
                right_room = min(right_room, (ox0 - sticky.x - sticky.width - STICKY_MIN_GAP) / 2.0)
        for node_key, (nx, _ny) in positions.items():
            node = by_key.get(node_key)
            if _effective_section(node, by_key) == sticky.key:
                continue
            nx1 = nx + node_width(node)
            if nx1 <= sticky.x:
                left_room = min(left_room, sticky.x - nx1 - STICKY_MIN_GAP)
            elif nx >= sticky.x + sticky.width:
                right_room = min(right_room, nx - sticky.x - sticky.width - STICKY_MIN_GAP)
        half = need / 2.0
        grow_left = max(0.0, min(half, left_room))
        grow_right = max(0.0, min(need - grow_left, right_room))
        grow_left = max(0.0, min(need - grow_right, left_room))
        grow_left = int(grow_left // GRID) * GRID
        grow_right = int(grow_right // GRID) * GRID
        sticky.x -= grow_left
        sticky.width += grow_left + grow_right


def _place_overview(content: str, stickies: List[StickyRect],
                    positions: Dict[str, Tuple[int, int]],
                    by_key: Dict[str, Node]) -> StickyRect:
    """Left of every node and band, top-aligned with the bands."""
    lefts = [s.x for s in stickies] + [x for x, _y in positions.values()]
    tops = [s.y for s in stickies] + [y for _x, y in positions.values()]
    min_x = min(lefts) if lefts else 0
    top = min(tops) if tops else 0
    height = max(200, _snap_up(text_height(content, OVERVIEW_W) + 20))
    return StickyRect(key="__overview", label="Overview", note="", color=OVERVIEW_COLOR,
                      x=snap(min_x - OVERVIEW_GAP - OVERVIEW_W), y=snap(top),
                      width=OVERVIEW_W, height=height,
                      heading=text_height(content, OVERVIEW_W), content=content)


# --------------------------------------------------------------------------
# Invariants — imported by the test suite and by the CLI's self-check.
# --------------------------------------------------------------------------


def _overlaps(a: Tuple[int, int, int, int], b: Tuple[int, int, int, int]) -> bool:
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def check(spec: WorkflowSpec, placement: Placement) -> List[str]:
    """Return layout problems. Empty list means the canvas is clean."""
    problems: List[str] = []
    by_key = {n.key: n for n in spec.nodes}

    placed = [k for k in placement.positions]
    for i in range(len(placed)):
        for j in range(i + 1, len(placed)):
            a, b = placed[i], placed[j]
            if _overlaps(placement.bbox(a, by_key.get(a)), placement.bbox(b, by_key.get(b))):
                problems.append("nodes {!r} and {!r} overlap".format(a, b))

    for i in range(len(placement.stickies)):
        for j in range(i + 1, len(placement.stickies)):
            s, t = placement.stickies[i], placement.stickies[j]
            if _overlaps(
                (s.x, s.y, s.x + s.width, s.y + s.height),
                (t.x, t.y, t.x + t.width, t.y + t.height),
            ):
                problems.append("sections {!r} and {!r} overlap".format(s.key, t.key))

    # A section's text must end above every node, or the note runs into them.
    for sticky in placement.stickies:
        if not sticky.heading:
            continue
        head = (sticky.x, sticky.y, sticky.x + sticky.width, sticky.y + sticky.heading)
        for key in placed:
            if _overlaps(head, placement.bbox(key, by_key.get(key))):
                problems.append("node {!r} sits under the text of section {!r}".format(
                    key, sticky.key))

    if placement.overview is not None:
        o = placement.overview
        rect = (o.x, o.y, o.x + o.width, o.y + o.height)
        for key in placed:
            if _overlaps(rect, placement.bbox(key, by_key.get(key))):
                problems.append("overview sticky overlaps node {!r}".format(key))
        for sticky in placement.stickies:
            if _overlaps(rect, (sticky.x, sticky.y, sticky.x + sticky.width,
                                sticky.y + sticky.height)):
                problems.append("overview sticky overlaps section {!r}".format(sticky.key))

    for sticky in placement.stickies:
        rect = (sticky.x, sticky.y, sticky.x + sticky.width, sticky.y + sticky.height)
        for node in spec.nodes:
            section = _effective_section(node, by_key)
            if section != sticky.key or node.key not in placement.positions:
                continue
            box = placement.bbox(node.key, node)
            if not (
                box[0] >= rect[0] and box[1] >= rect[1] and box[2] <= rect[2] and box[3] <= rect[3]
            ):
                problems.append(
                    "node {!r} escapes its section {!r}".format(node.key, sticky.key)
                )

    # A left-to-right read is the whole visual premise. Edges explicitly marked
    # as loop-backs are exempt — those are meant to point left.
    for edge in spec.flow_edges:
        if edge.src in placement.columns and edge.dst in placement.columns:
            if placement.columns[edge.dst] <= placement.columns[edge.src]:
                problems.append(
                    "edge {} -> {} does not move rightward".format(edge.src, edge.dst)
                )

    return problems
