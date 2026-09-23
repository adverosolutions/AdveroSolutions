"""WorkflowSpec -> native Excalidraw scene (no external renderer).

Built directly from the same layout the n8n compiler uses, so the diagram can
never disagree with the workflow. Compared with the DSL renderer this one
draws what a person walking a client through the system wants on screen:

* one tinted band per stage, carrying the stage title and its note
* node shapes coloured by what they do (trigger, AI, action, gate, data, wait)
* gates as diamonds, with the branch label written on each arrow
* loop-backs as dashed arrows routed underneath the row
* AI sub-nodes (model, memory, tools, parser) as small pills under the parent

Everything is plain ASCII by construction (see ascii_safe in generate.py).
"""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional, Tuple

from .layout import (AI_NODE_H, NODE_H, layout, node_height, node_width)
from .spec import AI_SUB_KINDS, TRIGGER_KINDS, Node, WorkflowSpec

# Horizontal stretch from n8n coordinates (100px icon boxes) to Excalidraw
# boxes wide enough to hold a full label.
SX = 1.45
NODE_W = 280
NODE_H_EX = 84
GATE_W = 320
GATE_H = 140
SUB_W = 220
SUB_H = 44
FONT = 2            # Excalidraw: 1 = hand-drawn, 2 = Helvetica, 3 = mono
LABEL_SIZE = 15
TITLE_SIZE = 22
NOTE_SIZE = 13
SCENE_TITLE_SIZE = 30

# Stage band palette: (fill, stroke, title colour). Rotates by stage index.
BAND_PALETTE = [
    ("#e7f0fd", "#9db7e6", "#1e4f9c"),
    ("#e8f6ea", "#9fd1a8", "#1f6b30"),
    ("#f3e9fb", "#c7a6e3", "#5b2c8c"),
    ("#fff5df", "#e6c97a", "#8a5a00"),
    ("#e4f7f9", "#8fd0d8", "#0e5f6a"),
    ("#fdeae4", "#e8a58f", "#8f3416"),
]

# Node fill by what the node does.
def _node_style(node: Node) -> Tuple[str, str]:
    k = node.kind
    if k in TRIGGER_KINDS:
        return ("#b7e4c7", "#2d6a4f")
    if k.startswith("ai."):
        return ("#dcc7f2", "#5b2c8c")
    if k in ("flow.branch", "flow.switch"):
        return ("#ffe89a", "#8a5a00")
    if k == "flow.wait":
        return ("#ffd6a5", "#9c4a00")
    if k == "flow.noop":
        return ("#f1f1f1", "#6b6b6b")
    if k == "app.action":
        return ("#bcd8f7", "#1e4f9c")
    if k == "net.http":
        return ("#b5e5ec", "#0e5f6a")
    if k == "net.respond":
        return ("#e0d4c8", "#5c4630")
    return ("#e9e9e9", "#444444")      # data.* and anything else


def _wrap(text: str, width_px: int, size: int) -> str:
    per_line = max(8, int((width_px - 28) / (size * 0.56)))
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if len(trial) > per_line and cur:
            lines.append(cur)
            cur = w
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return "\n".join(lines)


class _Scene:
    def __init__(self) -> None:
        self.elements: List[Dict[str, Any]] = []
        self._rng = random.Random(7)
        self._n = 0

    def _id(self, prefix: str) -> str:
        self._n += 1
        return "{}_{}".format(prefix, self._n)

    def _base(self, kind: str, x: float, y: float, w: float, h: float, **kw: Any) -> Dict[str, Any]:
        el = {
            "id": self._id(kind), "type": kind,
            "x": round(x), "y": round(y), "width": round(w), "height": round(h),
            "angle": 0, "strokeColor": "#1e1e1e", "backgroundColor": "transparent",
            "fillStyle": "solid", "strokeWidth": 1, "strokeStyle": "solid",
            "roughness": 0, "opacity": 100, "groupIds": [], "frameId": None,
            "roundness": None, "seed": self._rng.randint(1, 2**31),
            "version": 1, "versionNonce": self._rng.randint(1, 2**31),
            "isDeleted": False, "boundElements": [], "updated": 1, "link": None,
            "locked": False,
        }
        el.update(kw)
        self.elements.append(el)
        return el

    def rect(self, x, y, w, h, fill, stroke, radius=True, stroke_width=1, dashed=False):
        return self._base("rectangle", x, y, w, h, backgroundColor=fill, strokeColor=stroke,
                          strokeWidth=stroke_width, strokeStyle="dashed" if dashed else "solid",
                          roundness={"type": 3} if radius else None)

    def diamond(self, x, y, w, h, fill, stroke):
        return self._base("diamond", x, y, w, h, backgroundColor=fill, strokeColor=stroke,
                          strokeWidth=1, roundness={"type": 2})

    def text(self, x, y, w, content, size, color="#1e1e1e", align="left",
             container: Optional[Dict[str, Any]] = None, valign="top"):
        lines = content.count("\n") + 1
        h = lines * size * 1.25
        el = self._base("text", x, y, w, h, strokeColor=color, text=content,
                        fontSize=size, fontFamily=FONT, textAlign=align,
                        verticalAlign=valign, baseline=size, containerId=None,
                        originalText=content, lineHeight=1.25, autoResize=False)
        if container is not None:
            el["containerId"] = container["id"]
            el["textAlign"] = "center"
            el["verticalAlign"] = "middle"
            el["x"] = container["x"] + (container["width"] - w) / 2
            el["y"] = container["y"] + (container["height"] - h) / 2
            container["boundElements"].append({"type": "text", "id": el["id"]})
        return el

    def arrow(self, src, dst, points, color="#1e1e1e", dashed=False, label: Optional[str] = None,
              width=1.5):
        x0, y0 = points[0]
        rel = [[round(px - x0), round(py - y0)] for px, py in points]
        el = self._base("arrow", x0, y0,
                        max(abs(p[0]) for p in rel) or 1, max(abs(p[1]) for p in rel) or 1,
                        strokeColor=color, strokeWidth=width,
                        strokeStyle="dashed" if dashed else "solid",
                        roundness={"type": 2}, points=rel, lastCommittedPoint=None,
                        startBinding={"elementId": src["id"], "focus": 0, "gap": 4},
                        endBinding={"elementId": dst["id"], "focus": 0, "gap": 4},
                        startArrowhead=None, endArrowhead="arrow", elbowed=False)
        src["boundElements"].append({"type": "arrow", "id": el["id"]})
        dst["boundElements"].append({"type": "arrow", "id": el["id"]})
        if label:
            mid = points[len(points) // 2] if len(points) > 2 else (
                (points[0][0] + points[1][0]) / 2, (points[0][1] + points[1][1]) / 2)
            w = max(40, len(label) * 8 + 16)
            t = self.text(mid[0] - w / 2, mid[1] - 11, w, label, 13, color=color, align="center")
            t["containerId"] = el["id"]
            t["verticalAlign"] = "middle"
            el["boundElements"].append({"type": "text", "id": t["id"]})
        return el


def compile_excalidraw_scene(spec: WorkflowSpec) -> Dict[str, Any]:
    placement = layout(spec)
    scene = _Scene()
    by_key = {n.key: n for n in spec.nodes}
    boxes: Dict[str, Dict[str, Any]] = {}

    def ex(x: float) -> float:
        return x * SX

    # -- nodes ------------------------------------------------------------
    for node in spec.flow_nodes:
        if node.key not in placement.positions:
            continue
        px, py = placement.positions[node.key]
        cx = ex(px) + node_width(node) * SX / 2
        cy = py + NODE_H / 2
        fill, stroke = _node_style(node)
        if node.kind in ("flow.branch", "flow.switch"):
            box = scene.diamond(cx - GATE_W / 2, cy - GATE_H / 2, GATE_W, GATE_H, fill, stroke)
            scene.text(0, 0, GATE_W - 150, _wrap(node.label, GATE_W - 130, LABEL_SIZE - 1),
                       LABEL_SIZE - 1, color="#1e1e1e", container=box)
        else:
            box = scene.rect(cx - NODE_W / 2, cy - NODE_H_EX / 2, NODE_W, NODE_H_EX, fill, stroke,
                             stroke_width=1.5 if node.kind in TRIGGER_KINDS else 1)
            scene.text(0, 0, NODE_W - 24, _wrap(node.label, NODE_W, LABEL_SIZE), LABEL_SIZE,
                       color="#1e1e1e", container=box)
        boxes[node.key] = box

    # -- AI sub-nodes as pills under the parent ------------------------------
    pills: Dict[str, Dict[str, Any]] = {}
    for node in spec.nodes:
        if node.kind not in AI_SUB_KINDS or not node.parent or node.parent not in boxes:
            continue
        if node.key not in placement.positions:
            continue
        px, py = placement.positions[node.key]
        cx = ex(px) + node_width(node) * SX / 2
        top = py + 30
        pill = scene.rect(cx - SUB_W / 2, top, SUB_W, SUB_H, "#efe6fa", "#7b4bb5")
        pills[node.key] = pill
        scene.text(0, 0, SUB_W - 20, _wrap(node.label, SUB_W, 12), 12, color="#3b1f5e", container=pill)
        parent = boxes[node.parent]
        scene.arrow(parent, pill, [(parent["x"] + parent["width"] / 2, parent["y"] + parent["height"]),
                                   (cx, top)], color="#7b4bb5", dashed=True, width=1)

    # -- stage bands, sized from the boxes actually drawn --------------------
    band_elements: List[Dict[str, Any]] = []
    section_of = {n.key: n.section for n in spec.flow_nodes}
    for sub in spec.nodes:
        if sub.kind in AI_SUB_KINDS and sub.parent:
            section_of[sub.key] = section_of.get(sub.parent)
    all_boxes = dict(boxes)
    all_boxes.update(pills)
    for i, st in enumerate(placement.stickies):
        members = [all_boxes[k] for k in all_boxes if section_of.get(k) == st.key]
        if not members:
            continue
        fill, stroke, title_col = BAND_PALETTE[i % len(BAND_PALETTE)]
        min_x = min(m["x"] for m in members) - 36
        max_x = max(m["x"] + m["width"] for m in members) + 36
        min_y = min(m["y"] for m in members)
        max_y = max(m["y"] + m["height"] for m in members) + 36
        bw = max_x - min_x
        title = _wrap(st.label, int(bw), TITLE_SIZE)
        note = _wrap(st.note, int(bw), NOTE_SIZE) if st.note else ""
        head_h = 20 + (title.count("\n") + 1) * TITLE_SIZE * 1.25
        if note:
            head_h += 8 + (note.count("\n") + 1) * NOTE_SIZE * 1.25
        by = min_y - head_h - 26
        before = len(scene.elements)
        band = scene.rect(min_x, by, bw, max_y - by, fill, stroke, radius=True, stroke_width=1)
        scene.text(min_x + 22, by + 16, bw - 44, title, TITLE_SIZE, color=title_col)
        if note:
            scene.text(min_x + 22, by + 16 + (title.count("\n") + 1) * TITLE_SIZE * 1.25 + 8,
                       bw - 44, note, NOTE_SIZE, color="#4a4a4a")
        band_elements.extend(scene.elements[before:])
        del scene.elements[before:]
    scene.elements[0:0] = band_elements

    # -- edges -----------------------------------------------------------
    for e in spec.edges:
        if e.src not in boxes or e.dst not in boxes:
            continue
        a, b = boxes[e.src], boxes[e.dst]
        ax, ay = a["x"] + a["width"], a["y"] + a["height"] / 2
        bx, by = b["x"], b["y"] + b["height"] / 2
        label = e.branch
        if e.loop:
            # route underneath: drop from src bottom, run back, rise to dst bottom
            drop = max(a["y"] + a["height"], b["y"] + b["height"]) + 70
            pts = [(a["x"] + a["width"] / 2, a["y"] + a["height"]),
                   (a["x"] + a["width"] / 2, drop),
                   (b["x"] + b["width"] / 2, drop),
                   (b["x"] + b["width"] / 2, b["y"] + b["height"])]
            scene.arrow(a, b, pts, color="#8a5a00", dashed=True, label=label or "loop")
            continue
        if bx <= ax:
            # backwards on the page without being marked a loop: route below too
            drop = max(a["y"] + a["height"], b["y"] + b["height"]) + 60
            pts = [(a["x"] + a["width"] / 2, a["y"] + a["height"]),
                   (a["x"] + a["width"] / 2, drop),
                   (b["x"] + b["width"] / 2, drop),
                   (b["x"] + b["width"] / 2, b["y"] + b["height"])]
            scene.arrow(a, b, pts, color="#555555", dashed=True, label=label)
            continue
        if abs(ay - by) < 4:
            pts = [(ax, ay), (bx, by)]
        else:
            mx = ax + (bx - ax) / 2
            pts = [(ax, ay), (mx, ay), (mx, by), (bx, by)]
        color = "#1e1e1e"
        if label:
            low = label.lower()
            color = "#2d6a4f" if low in ("true", "yes") else "#a63c06" if low in ("false", "no") else "#1e4f9c"
        scene.arrow(a, b, pts, color=color, label=label)

    # -- scene title -----------------------------------------------------
    if scene.elements:
        min_x = min(el["x"] for el in scene.elements)
        min_y = min(el["y"] for el in scene.elements)
        scene.text(min_x, min_y - 70, 1200, spec.title, SCENE_TITLE_SIZE, color="#1e1e1e")

    return {
        "type": "excalidraw", "version": 2, "source": "upwork-workflow-generator",
        "elements": scene.elements,
        "appState": {"viewBackgroundColor": "#ffffff", "gridSize": None},
        "files": {},
    }
