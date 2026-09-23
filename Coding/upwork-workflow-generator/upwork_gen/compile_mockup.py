"""A fifth compile target: the GoHighLevel / Zapier builder, as HTML.

GoHighLevel and Zapier have no importable workflow format, so for those
postings there is nothing to paste into a canvas. This renders the same spec as
a page that reads like the builder itself, which gets the same beat in a Loom.

The interesting work is **flattening**. `WorkflowSpec` is a graph; these two
products are a vertical card stack that splits and never rejoins. So the graph
is walked into a stack, and where it forks each arm is walked to its own end —
the same choice compile_make.py makes for routers, and for the same reason:
neither product has a merge.

Every node in the spec reaches the page. Flow nodes become cards, AI sub-nodes
become chips on their parent's card. That is what keeps this honest against the
n8n file and the diagram, which a client sees in the same recording.
"""

from __future__ import annotations

import html
import json
from typing import Any, Dict, List, Optional, Set, Tuple

from .mockup_theme import initials, theme_for, tile_color
from .spec import (AI_SUB_KINDS, APP_KINDS, DATA_KINDS, TRIGGER_KINDS, Node,
                   WorkflowSpec)

# A safety rail on the walk. No real posting produces a chain this long, so
# hitting it means a cycle slipped past the loop-edge filter.
_MAX_CHAIN = 60

# kind -> the small grey word above a card title. Both builders label the role
# of every card; its absence is what makes a mockup feel like a diagram.
_KICKER = {
    "flow.branch": "Condition",
    "flow.switch": "Condition",
    "flow.wait": "Delay",
    "flow.noop": "Action",
    "data.filter": "Filter",
    "data.code": "Code",
    "net.http": "Action",
    "net.respond": "Action",
}

_NATIVE_GLYPH = {
    "flow.branch": "⑂", "flow.switch": "⑂", "flow.wait": "◷",
    "data.filter": "▽", "data.code": "{ }", "data.transform": "⇄",
    "data.merge": "⇥", "data.split": "⇤", "data.aggregate": "∑",
    "flow.noop": "•",
}

# What a chip says about a sub-node docked on an agent.
_CHIP = {
    "ai.model": "Model", "ai.memory": "Memory", "ai.tool": "Tool",
    "ai.embed": "Embeddings", "ai.vectorstore": "Vector Store",
    "ai.parser": "Parser",
}


def _kicker(node: Node) -> str:
    if node.kind in TRIGGER_KINDS:
        return "Trigger"
    if node.kind.startswith("ai."):
        return "AI Step"
    if node.kind in _KICKER:
        return _KICKER[node.kind]
    if node.kind in DATA_KINDS:
        return "Action"
    return "Action"


def _esc(text: Any) -> str:
    return html.escape(str(text), quote=True)


# --------------------------------------------------------------------------
# Flattening the graph into a card stack
# --------------------------------------------------------------------------

class _Card:
    """A node plus the arms hanging off it, if it forks."""

    __slots__ = ("node", "arms")

    def __init__(self, node: Node,
                 arms: Optional[List[Tuple[str, List["_Card"]]]] = None) -> None:
        self.node = node
        self.arms = arms or []


def _flatten(spec: WorkflowSpec,
             start_key: Optional[str] = None) -> Tuple[Optional[Node], List[_Card]]:
    """Walk the spec into (trigger, stack). Sub-nodes are excluded."""
    by_key = {n.key: n for n in spec.nodes}
    outgoing: Dict[str, List[Any]] = {}
    incoming: Set[str] = set()
    for edge in spec.edges:
        if getattr(edge, "loop", False):
            continue  # A back-edge has no place in a linear card stack.
        outgoing.setdefault(edge.src, []).append(edge)
        incoming.add(edge.dst)

    flow_nodes = [n for n in spec.nodes if n.kind not in AI_SUB_KINDS]
    if not flow_nodes:
        return None, []

    if start_key is not None:
        start = by_key.get(start_key) or flow_nodes[0]
    else:
        start = next((n for n in flow_nodes if n.kind in TRIGGER_KINDS), None)
        if start is None:
            start = next((n for n in flow_nodes if n.key not in incoming),
                         flow_nodes[0])

    def walk(key: str, depth: int) -> List[_Card]:
        stack: List[_Card] = []
        current: Optional[str] = key
        seen: Set[str] = set()
        while current and depth + len(stack) < _MAX_CHAIN:
            if current in seen:      # Defence in depth against a cycle.
                break
            seen.add(current)
            node = by_key.get(current)
            if node is None:
                break
            edges = outgoing.get(current, [])
            if len(edges) > 1:
                arms = [
                    (getattr(e, "branch", None) or "Path {}".format(i + 1),
                     walk(e.dst, depth + len(stack) + 1))
                    for i, e in enumerate(edges)
                ]
                stack.append(_Card(node, arms))
                break
            stack.append(_Card(node))
            current = edges[0].dst if edges else None
        return stack

    stack = walk(start.key, 0)
    # The trigger is drawn as its own card above the stack.
    return start, stack[1:] if stack and stack[0].node.key == start.key else stack


def _flatten_all(spec: WorkflowSpec) -> List[Tuple[Optional[Node], List[_Card]]]:
    """One (trigger, stack) per entry point.

    A spec with several triggers is several workflows — GoHighLevel and Zapier
    model them exactly that way, one workflow per trigger — and drawing only the
    first silently drops every node behind the others. That is invisible on the
    page and only shows up when the client compares it to the diagram.
    """
    incoming = {e.dst for e in spec.edges if not getattr(e, "loop", False)}
    flow_nodes = [n for n in spec.nodes if n.kind not in AI_SUB_KINDS]
    if not flow_nodes:
        return []

    roots = [n for n in flow_nodes if n.kind in TRIGGER_KINDS]
    roots += [n for n in flow_nodes
              if n.kind not in TRIGGER_KINDS and n.key not in incoming]
    if not roots:
        roots = [flow_nodes[0]]

    groups: List[Tuple[Optional[Node], List[_Card]]] = []
    covered: Set[str] = set()
    for root in roots:
        if root.key in covered:
            continue
        trigger, stack = _flatten(spec, start_key=root.key)
        covered.add(root.key)
        for card in _walk_cards(stack):
            covered.add(card.node.key)
        groups.append((trigger, stack))
    return groups


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------

class _Renderer:
    def __init__(self, spec: WorkflowSpec, theme_name: str,
                 account: str = "") -> None:
        self.spec = spec
        self.theme = theme_for(theme_name)
        self.account = account
        self._index = 0
        self.groups = _flatten_all(spec)
        self.trigger, self.stack = self.groups[0] if self.groups else (None, [])
        # Sub-nodes chain: embeddings dock on a vector store, which itself docks
        # on the agent. Only the agent gets a card, so every sub-node must be
        # resolved up to its nearest carded ancestor or it silently vanishes —
        # which is exactly the divergence the client notices between tabs.
        by_key = {n.key: n for n in spec.nodes}
        self._subs: Dict[str, List[Node]] = {}
        for node in spec.nodes:
            if node.kind not in AI_SUB_KINDS:
                continue
            owner, hops = node.parent, 0
            while owner in by_key and by_key[owner].kind in AI_SUB_KINDS and hops < 8:
                owner, hops = by_key[owner].parent, hops + 1
            if owner:
                self._subs.setdefault(owner, []).append(node)
        # The output sample belongs at the bottom of the LAST workflow drawn,
        # so the eye finishes on it.
        last_trigger, last_stack = self.groups[-1] if self.groups else (None, [])
        self._last_key = self._deepest(last_stack) or (
            last_trigger.key if last_trigger else None)

    def _deepest(self, stack: List[_Card]) -> Optional[str]:
        """The visually lowest card — the bottom of the longest arm."""
        if not stack:
            return self.trigger.key if self.trigger else None
        tail = stack[-1]
        if tail.arms:
            filled = [arm for _, arm in tail.arms if arm]
            if filled:
                return self._deepest(max(filled, key=len))
        return tail.node.key

    # -- pieces ------------------------------------------------------------
    def _tile(self, node: Node) -> str:
        app = node.app or ""
        if not app and node.kind in _NATIVE_GLYPH:
            return '<div class="tile tile-native">{}</div>'.format(
                _NATIVE_GLYPH[node.kind])
        if not app and node.kind in TRIGGER_KINDS:
            app = "Webhook"
        return '<div class="tile" style="background:{}">{}</div>'.format(
            tile_color(app), _esc(initials(app)))

    def _chips(self, node: Node) -> str:
        subs = self._subs.get(node.key, [])
        if not subs:
            return ""
        items = "".join(
            '<span class="chip"><b>{}</b> {}</span>'.format(
                _esc(_CHIP.get(s.kind, "Attached")), _esc(s.label))
            for s in subs
        )
        return '<div class="chips">{}</div>'.format(items)

    def _data(self, sample: Dict[str, Any]) -> str:
        if not sample:
            return ""
        rows = []
        for key, value in sample.items():
            if isinstance(value, (dict, list)):
                shown = json.dumps(value, ensure_ascii=False)
            elif isinstance(value, bool):
                shown = "true" if value else "false"
            else:
                shown = str(value)
            if len(shown) > 60:
                shown = shown[:57] + "…"
            rows.append('<div class="drow"><span class="dkey">{}</span>'
                        '<span class="dval">{}</span></div>'.format(
                            _esc(key), _esc(shown)))
        return ('<div class="data"><div class="dhead">{}</div>'
                '<div class="dbody">{}</div></div>').format(
                    _esc(self.theme["data_label"]), "".join(rows))

    def _mark(self) -> str:
        # Zapier ticks every validated step; GoHighLevel shows a row menu.
        return ('<div class="cmark">✓</div>' if self.theme["numbered"]
                else '<div class="cmenu">⋯</div>')

    def _card(self, node: Node, *, is_trigger: bool = False,
              data: str = "") -> str:
        number = ""
        if self.theme["numbered"]:
            self._index += 1
            number = '<span class="num">{}.</span> '.format(self._index)
        app = ('<span class="capp"> · {}</span>'.format(_esc(node.app))
               if node.app else "")
        note = ('<div class="cnote">{}</div>'.format(_esc(node.notes))
                if node.notes else "")
        return (
            '<div class="card{trig}"><div class="cmain">{tile}<div class="ctext">'
            '<div class="ckick">{num}{kick}{app}</div>'
            '<div class="ctitle">{title}</div>{note}{chips}</div>{mark}</div>'
            '{data}</div>'
        ).format(
            trig=" card-trigger" if is_trigger else "", tile=self._tile(node),
            num=number, kick=_esc(_kicker(node)), app=app,
            title=_esc(node.label), note=note, chips=self._chips(node),
            mark=self._mark(), data=data,
        )

    def _conn(self) -> str:
        return ('<div class="conn"><div class="cline"></div>'
                '<div class="cplus">+</div><div class="cline"></div></div>')

    def _stub(self) -> str:
        return '<div class="conn conn-end"><div class="cline"></div></div>'

    def _render_card(self, card: _Card) -> str:
        data = ""
        if card.node.key == self._last_key:
            data = self._data(self.spec.output_sample)
        html_out = self._card(card.node, data=data)
        if not card.arms:
            return html_out

        # Arms are laid out evenly, so the horizontal rule spans from the
        # centre of the first arm to the centre of the last.
        inset = 50.0 / max(len(card.arms), 1)
        arms = "".join(self._arm(label, arm) for label, arm in card.arms)
        return (html_out
                + '<div class="conn conn-split"><div class="cline"></div></div>'
                + '<div class="arms" style="--inset:{:.4f}%">{}</div>'.format(
                    inset, arms))

    def _arm(self, label: str, cards: List[_Card]) -> str:
        if cards:
            body = self._conn().join(self._render_card(c) for c in cards)
            body += self._stub()
        else:
            body = ('<div class="card card-empty"><div class="cmain">'
                    '<div class="ctext"><div class="ctitle-muted">'
                    'End automation</div></div></div></div>')
        return '<div class="arm"><div class="apill">{}</div>{}</div>'.format(
            _esc(_branch_label(label)), body)

    # -- page --------------------------------------------------------------
    def _topbar(self) -> str:
        theme = self.theme
        tabs = ""
        if theme["tabs"]:
            tabs = '<div class="tabs">{}</div>'.format("".join(
                '<div class="tab{}">{}</div>'.format(
                    " tab-on" if i == 0 else "", _esc(t))
                for i, t in enumerate(theme["tabs"])))  # type: ignore[arg-type]
        pill = ('<div class="toggle"><span class="tdot"></span>'
                '<span class="tlabel">Draft</span></div>'
                if theme["draft_pill"] else "")
        account = ('<div class="acct">{}</div>'.format(_esc(self.account))
                   if self.account else "")
        return (
            '<div class="topbar"><div class="tleft"><div class="back">‹</div>'
            '<div class="wname">{title}</div>{acct}</div>{tabs}'
            '<div class="tright">{pill}<button class="btn-ghost">Save</button>'
            '<button class="btn-primary">{publish}</button></div></div>'
        ).format(title=_esc(self.spec.title), acct=account, tabs=tabs,
                 pill=pill, publish=_esc(theme["publish"]))

    def render(self) -> str:
        parts = []
        for index, (trigger, stack) in enumerate(self.groups):
            if index:
                # Each trigger is its own workflow in these builders. Labelling
                # the break is honest and reads better than one impossible
                # stack with two starts.
                parts.append(
                    '<div class="wsplit"><span>Workflow {}</span></div>'.format(
                        index + 1))
            if trigger:
                data = self._data(self.spec.input_sample) if index == 0 else ""
                parts.append(self._card(trigger, is_trigger=True, data=data))
            for card in stack:
                parts.append(self._conn())
                parts.append(self._render_card(card))
            if not (stack and stack[-1].arms):
                parts.append(self._stub())

        wide = any(c.arms for _, stack in self.groups
                   for c in _walk_cards(stack))
        return _PAGE.format(
            title=_esc(self.spec.title),
            css=_css(self.theme, wide=wide),
            topbar=self._topbar(),
            body="".join(parts),
        )


def _walk_cards(stack: List[_Card]):
    for card in stack:
        yield card
        for _, arm in card.arms:
            for inner in _walk_cards(arm):
                yield inner


def _branch_label(label: str) -> str:
    """n8n speaks true/false; a client reads Yes/No."""
    mapping = {"true": "Yes", "false": "No"}
    return mapping.get(str(label).strip().lower(), label)


def _css(theme: Dict[str, object], wide: bool = False) -> str:
    grid = ""
    if theme["grid"]:
        grid = ("background-image:radial-gradient(circle,{}55 1px,transparent 1px);"
                "background-size:22px 22px;".format(theme["line"]))
    return _CSS.format(
        accent=theme["accent"], accent_soft=theme["accent_soft"],
        canvas=theme["canvas"], card=theme["card"], border=theme["border"],
        text=theme["text"], muted=theme["muted"], line=theme["line"],
        radius=theme["radius"], card_w=theme["card_w"], grid=grid,
        col_w="880px" if wide else theme["card_w"],
    )


_CSS = """
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Inter,Roboto,
  'Helvetica Neue',Arial,sans-serif;color:{text};background:{canvas};
  -webkit-font-smoothing:antialiased}}

.topbar{{display:flex;align-items:center;justify-content:space-between;gap:24px;
  background:#fff;border-bottom:1px solid {border};padding:0 20px;height:56px;
  position:sticky;top:0;z-index:20}}
.tleft{{display:flex;align-items:center;gap:12px;min-width:0}}
.back{{width:28px;height:28px;border:1px solid {border};border-radius:6px;
  display:flex;align-items:center;justify-content:center;color:{muted};
  font-size:18px;line-height:1;flex:none}}
.wname{{font-size:15px;font-weight:600;white-space:nowrap;overflow:hidden;
  text-overflow:ellipsis}}
.wsplit{{display:flex;align-items:center;gap:10px;margin:34px 0 26px;
  color:{muted};font-size:11px;letter-spacing:.09em;text-transform:uppercase}}
.wsplit::before,.wsplit::after{{content:'';flex:1;height:1px;background:{border}}}
.acct{{font-size:12px;color:{muted};background:{canvas};border:1px solid {border};
  padding:3px 8px;border-radius:20px;white-space:nowrap}}
.tabs{{display:flex;gap:26px;height:100%;align-items:stretch}}
.tab{{display:flex;align-items:center;font-size:13px;color:{muted};
  border-bottom:2px solid transparent;white-space:nowrap}}
.tab-on{{color:{accent};border-bottom-color:{accent};font-weight:600}}
.tright{{display:flex;align-items:center;gap:10px}}
.toggle{{display:flex;align-items:center;gap:6px;border:1px solid {border};
  border-radius:20px;padding:4px 10px 4px 8px}}
.tdot{{width:8px;height:8px;border-radius:50%;background:#f0b429;display:block}}
.tlabel{{font-size:12px;color:{muted}}}
.btn-ghost{{font:inherit;font-size:13px;color:{text};background:#fff;
  border:1px solid {border};border-radius:6px;padding:7px 14px}}
.btn-primary{{font:inherit;font-size:13px;font-weight:600;color:#fff;
  background:{accent};border:0;border-radius:6px;padding:8px 16px}}

.canvas{{padding:44px 24px 90px;display:flex;justify-content:center;{grid}}}
.column{{width:{col_w};max-width:100%;display:flex;flex-direction:column;
  align-items:stretch}}
.column > .card{{width:100%;max-width:{card_w};align-self:center}}

.card{{background:{card};border:1px solid {border};border-radius:{radius};
  box-shadow:0 1px 2px rgba(16,24,40,.05),0 1px 3px rgba(16,24,40,.04)}}
.card-trigger{{border-color:{accent}66;box-shadow:0 0 0 3px {accent_soft},
  0 1px 3px rgba(16,24,40,.06)}}
.cmain{{display:flex;align-items:center;gap:12px;padding:14px}}
.tile{{width:38px;height:38px;border-radius:8px;flex:none;color:#fff;
  font-size:13px;font-weight:700;letter-spacing:.3px;display:flex;
  align-items:center;justify-content:center}}
.tile-native{{background:{canvas};border:1px solid {border};color:{muted};
  font-size:15px;font-weight:500}}
.ctext{{flex:1;min-width:0}}
.ckick{{font-size:11px;font-weight:600;letter-spacing:.4px;color:{muted};
  text-transform:uppercase;margin-bottom:3px;white-space:nowrap;overflow:hidden;
  text-overflow:ellipsis}}
.capp{{font-weight:500;letter-spacing:.2px}}
.num{{color:{accent}}}
.ctitle{{font-size:14px;font-weight:600;line-height:1.3}}
.ctitle-muted{{font-size:13px;color:{muted};padding:2px 0}}
.cnote{{font-size:12px;color:{muted};line-height:1.45;margin-top:3px}}
.chips{{display:flex;flex-wrap:wrap;gap:6px;margin-top:7px}}
.chip{{font-size:10.5px;color:{muted};background:{canvas};border:1px solid {border};
  border-radius:5px;padding:2px 7px;white-space:nowrap}}
.chip b{{color:{text};font-weight:600}}
.cmark{{width:18px;height:18px;border-radius:50%;background:#12b76a;color:#fff;
  font-size:11px;display:flex;align-items:center;justify-content:center;flex:none}}
.cmenu{{width:18px;color:{muted};font-size:16px;line-height:1;text-align:center;
  flex:none}}
.card-empty{{background:transparent;border-style:dashed;box-shadow:none}}
.card-empty .cmain{{padding:10px 14px;justify-content:center}}

.data{{border-top:1px solid {border};padding:10px 14px 12px}}
.dhead{{font-size:10px;font-weight:700;letter-spacing:.6px;color:{muted};
  text-transform:uppercase;margin-bottom:7px}}
.dbody{{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
  font-size:11.5px;line-height:1.75}}
.drow{{display:flex;gap:10px}}
.dkey{{color:{muted};flex:none;min-width:104px}}
.dval{{color:{text};overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}

.conn{{display:flex;flex-direction:column;align-items:center}}
.cline{{width:2px;height:15px;background:{line}}}
.conn-end .cline{{height:26px}}
.conn-split .cline{{height:20px}}
.cplus{{width:22px;height:22px;border-radius:50%;background:#fff;
  border:1px solid {line};color:{muted};font-size:14px;line-height:1;
  display:flex;align-items:center;justify-content:center}}

.arms{{display:flex;gap:26px;position:relative;padding-top:30px;--inset:25%}}
.arms::before{{content:"";position:absolute;top:0;left:var(--inset);
  right:var(--inset);height:2px;background:{line}}}
.arm{{flex:1;min-width:0;display:flex;flex-direction:column;position:relative}}
.arm::before{{content:"";position:absolute;top:-30px;left:50%;width:2px;
  height:30px;background:{line}}}
.apill{{align-self:center;font-size:11px;font-weight:700;letter-spacing:.4px;
  text-transform:uppercase;color:{accent};background:#fff;border:1px solid {line};
  border-radius:20px;padding:3px 12px;margin-bottom:14px;position:relative;
  z-index:1;max-width:100%;overflow:hidden;text-overflow:ellipsis;
  white-space:nowrap}}
.arm .cmain{{padding:12px 13px}}
.arm .tile{{width:34px;height:34px;font-size:12px}}
.arm .ctitle{{font-size:13.5px}}

/* A recording window is rarely full width. Drop optional chrome rather than
   let it overlap the workflow name, the one label the client actually reads. */
@media (max-width:1180px){{ .tabs{{display:none}} }}
@media (max-width:820px){{ .acct{{display:none}} .btn-ghost{{display:none}} }}
@media (max-width:560px){{
  .canvas{{padding:28px 12px 70px}}
  .column{{width:100%}}
  .arms{{gap:12px}}
}}
"""

_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>{css}</style></head>
<body>{topbar}<div class="canvas"><div class="column">{body}</div></div></body>
</html>"""


def theme_for_platform(platform: str) -> str:
    """Which builder to draw. Anything that is not Zapier reads as GHL."""
    return "zapier" if platform == "zapier" else "ghl"


def compile_mockup(spec: WorkflowSpec, theme: Optional[str] = None,
                   account: str = "") -> str:
    return _Renderer(spec, theme or theme_for_platform(spec.platform),
                     account).render()
