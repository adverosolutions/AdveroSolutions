"""Spec -> one self-contained HTML file that reads as the real builder.

Self-contained is a hard requirement, not a preference. The page is opened in a
browser tab during a recording; a stylesheet or font that fails to load would
repaint the layout on camera. So: no external requests, system font stack,
everything inline.

Layout is a centred vertical stack because that is what both builders are. The
only non-trivial geometry is the branch split, which is drawn with two absolute
rules rather than SVG so it survives any zoom the browser is set to.
"""

from __future__ import annotations

import html
import json
from typing import Any, Dict, List, Optional

from .spec import MockupSpec, Step
from .theme import initials, theme_for, tile_color

# Type -> the small grey word above the card title. Real builders label the
# role of every card, and its absence is one of the first things that makes a
# mockup feel like a diagram instead of a product.
KICKER = {
    "action": "Action",
    "ai": "AI Step",
    "branch": "Condition",
    "wait": "Delay",
    "filter": "Filter",
    "code": "Code",
}


def _esc(text: Any) -> str:
    return html.escape(str(text), quote=True)


def _sample_rows(sample: Dict[str, Any]) -> str:
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
        rows.append(
            '<div class="drow"><span class="dkey">{}</span>'
            '<span class="dval">{}</span></div>'.format(_esc(key), _esc(shown))
        )
    return "".join(rows)


def _data_panel(sample: Dict[str, Any], label: str) -> str:
    if not sample:
        return ""
    return (
        '<div class="data"><div class="dhead">{}</div><div class="dbody">{}</div></div>'
    ).format(_esc(label), _sample_rows(sample))


def _tile(app: str, step_type: str) -> str:
    """The coloured square on the left of a card.

    Non-app steps (delay, condition, filter, code) get a glyph instead of
    initials, matching how both builders render their own primitives.
    """
    glyphs = {"wait": "◷", "branch": "⑂", "filter": "▽", "code": "{ }"}
    if step_type in glyphs and not app:
        return ('<div class="tile tile-native">{}</div>'.format(glyphs[step_type]))
    return '<div class="tile" style="background:{}">{}</div>'.format(
        tile_color(app), _esc(initials(app))
    )


class _Renderer:
    def __init__(self, spec: MockupSpec) -> None:
        self.spec = spec
        self.theme = theme_for(spec.platform)
        self._index = 0
        # Identified while walking so the output sample lands on the visually
        # last card, whichever arm of a branch that turns out to be.
        self._last_card_id = self._find_last_card_id()

    # -- numbering ---------------------------------------------------------
    def _next_number(self) -> str:
        self._index += 1
        return str(self._index)

    def _find_last_card_id(self) -> int:
        """id() of the final step in reading order, branches included."""
        def last_of(steps: List[Step]) -> Optional[Step]:
            if not steps:
                return None
            tail = steps[-1]
            if tail.is_branch:
                # The visually lowest card is the bottom of the longer arm.
                arms = [a for a in (tail.yes, tail.no) if a]
                if arms:
                    deepest = max(arms, key=len)
                    return last_of(deepest) or tail
            return tail

        final = last_of(self.spec.steps)
        return id(final) if final else 0

    # -- cards -------------------------------------------------------------
    def _card(self, *, app: str, title: str, kicker: str, note: str,
              step_type: str, data: str = "", is_trigger: bool = False) -> str:
        number = ""
        if self.theme["numbered"]:
            number = '<span class="num">{}.</span> '.format(self._next_number())

        classes = "card"
        if is_trigger:
            classes += " card-trigger"

        app_line = ""
        if app:
            app_line = '<span class="capp"> · {}</span>'.format(_esc(app))

        note_line = ""
        if note:
            note_line = '<div class="cnote">{}</div>'.format(_esc(note))

        return (
            '<div class="{cls}">'
            '<div class="cmain">{tile}'
            '<div class="ctext">'
            '<div class="ckick">{num}{kick}{app}</div>'
            '<div class="ctitle">{title}</div>{note}'
            '</div>'
            '{mark}'
            '</div>{data}</div>'
        ).format(
            cls=classes, tile=_tile(app, step_type), num=number,
            kick=_esc(kicker), app=app_line, title=_esc(title),
            note=note_line, data=data, mark=self._mark(),
        )

    def _mark(self) -> str:
        """Zapier ticks every validated step; GoHighLevel shows a row menu.

        Small, but it is the kind of detail a client who uses the product every
        day registers without being able to say why something looked off.
        """
        if self.theme["numbered"]:
            return '<div class="cmark">✓</div>'
        return '<div class="cmenu">⋯</div>'

    def _connector(self) -> str:
        return ('<div class="conn"><div class="cline"></div>'
                '<div class="cplus">+</div><div class="cline"></div></div>')

    def _stub(self) -> str:
        """A short tail below the final card, as both builders draw."""
        return '<div class="conn conn-end"><div class="cline"></div></div>'

    def _step(self, step: Step) -> str:
        if step.is_branch:
            return self._branch(step)

        data = ""
        if id(step) == self._last_card_id:
            data = _data_panel(self.spec.output_sample, str(self.theme["data_label"]))

        return self._card(
            app=step.app, title=step.label, kicker=KICKER.get(step.type, "Action"),
            note=step.note, step_type=step.type, data=data,
        )

    def _arm(self, label: str, steps: List[Step]) -> str:
        if steps:
            body = self._connector().join(self._step(s) for s in steps)
            body += self._stub()
        else:
            body = ('<div class="card card-empty"><div class="cmain">'
                    '<div class="ctext"><div class="ctitle-muted">'
                    'End automation</div></div></div></div>')
        return ('<div class="arm"><div class="apill">{}</div>{}</div>'
                .format(_esc(label), body))

    def _branch(self, step: Step) -> str:
        head = self._card(
            app=step.app, title=step.label, kicker=KICKER["branch"],
            note=step.note, step_type="branch",
        )
        yes_label, no_label = (step.branch_labels + ["Yes", "No"])[:2]
        arms = (self._arm(yes_label, step.yes) + self._arm(no_label, step.no))
        return (head + '<div class="conn conn-split"><div class="cline"></div></div>'
                + '<div class="arms">{}</div>'.format(arms))

    # -- chrome ------------------------------------------------------------
    def _topbar(self) -> str:
        theme = self.theme
        tabs = ""
        if theme["tabs"]:
            items = "".join(
                '<div class="tab{}">{}</div>'.format(
                    " tab-on" if i == 0 else "", _esc(t))
                for i, t in enumerate(theme["tabs"])  # type: ignore[arg-type]
            )
            tabs = '<div class="tabs">{}</div>'.format(items)

        pill = ""
        if theme["draft_pill"]:
            pill = ('<div class="toggle"><span class="tdot"></span>'
                    '<span class="tlabel">Draft</span></div>')

        account = ""
        if self.spec.account:
            account = '<div class="acct">{}</div>'.format(_esc(self.spec.account))

        return (
            '<div class="topbar">'
            '<div class="tleft"><div class="back">‹</div>'
            '<div class="wname">{title}</div>{acct}</div>'
            '{tabs}'
            '<div class="tright">{pill}<button class="btn-ghost">Save</button>'
            '<button class="btn-primary">{publish}</button></div>'
            '</div>'
        ).format(title=_esc(self.spec.title), acct=account, tabs=tabs,
                 pill=pill, publish=_esc(theme["publish"]))

    def _trigger(self) -> str:
        return self._card(
            app=self.spec.trigger.app, title=self.spec.trigger.label,
            kicker=str(self.theme["trigger_kicker"]), note=self.spec.trigger.note,
            step_type="action", is_trigger=True,
            data=_data_panel(self.spec.input_sample, str(self.theme["data_label"])),
        )

    def _body(self) -> str:
        parts = [self._trigger()]
        for step in self.spec.steps:
            parts.append(self._connector())
            parts.append(self._step(step))
        # A branch already ends each of its arms with a tail.
        if not self.spec.steps[-1].is_branch:
            parts.append(self._stub())
        return "".join(parts)

    def render(self) -> str:
        # A split needs room. Both builders widen the canvas when a path opens
        # rather than squeezing two columns into one card's width, and at
        # recording zoom the difference is the gap between readable and not.
        branches = any(s.is_branch for s in self.spec.walk())
        return _PAGE.format(
            title=_esc(self.spec.title),
            css=_css(self.theme, wide=branches),
            topbar=self._topbar(),
            body=self._body(),
        )


def _css(theme: Dict[str, object], wide: bool = False) -> str:
    grid = ""
    if theme["grid"]:
        grid = (
            "background-image:radial-gradient(circle,{line}55 1px,transparent 1px);"
            "background-size:22px 22px;".format(line=theme["line"])
        )
    return _CSS.format(
        accent=theme["accent"], accent_soft=theme["accent_soft"],
        canvas=theme["canvas"], card=theme["card"], border=theme["border"],
        text=theme["text"], muted=theme["muted"], line=theme["line"],
        radius=theme["radius"], card_w=theme["card_w"], grid=grid,
        col_w="760px" if wide else theme["card_w"],
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
/* Top-level cards keep a single-card width even on a widened canvas; only the
   split is allowed to use the extra room. */
.column > .card{{width:100%;max-width:{card_w};align-self:center}}

.card{{background:{card};border:1px solid {border};border-radius:{radius};
  box-shadow:0 1px 2px rgba(16,24,40,.05),0 1px 3px rgba(16,24,40,.04)}}
.card-trigger{{border-color:{accent}66;box-shadow:0 0 0 3px {accent_soft},
  0 1px 3px rgba(16,24,40,.06)}}
.cmain{{display:flex;align-items:center;gap:12px;padding:14px 14px}}
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
.cmark{{width:18px;height:18px;border-radius:50%;background:#12b76a;color:#fff;
  font-size:11px;display:flex;align-items:center;justify-content:center;flex:none}}
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

.arms{{display:flex;gap:32px;position:relative;padding-top:30px}}
.arms::before{{content:"";position:absolute;top:0;left:25%;right:25%;height:2px;
  background:{line}}}
.arm{{flex:1;min-width:0;display:flex;flex-direction:column;position:relative}}
.arm::before{{content:"";position:absolute;top:-30px;left:50%;width:2px;
  height:30px;background:{line}}}
.apill{{align-self:center;font-size:11px;font-weight:700;letter-spacing:.4px;
  text-transform:uppercase;color:{accent};background:#fff;border:1px solid {line};
  border-radius:20px;padding:3px 12px;margin-bottom:14px;position:relative;z-index:1}}
.arm .cmain{{padding:12px 13px}}
.arm .tile{{width:34px;height:34px;font-size:12px}}
.arm .ctitle{{font-size:13.5px}}
.cmenu{{width:18px;color:{muted};font-size:16px;line-height:1;text-align:center;
  flex:none}}

/* A recording window is rarely full width. Drop the optional chrome rather
   than let it overlap the workflow name, which is the one label the client
   actually reads. */
@media (max-width:1180px){{ .tabs{{display:none}} }}
@media (max-width:820px){{ .acct{{display:none}} .btn-ghost{{display:none}} }}
@media (max-width:560px){{
  .canvas{{padding:28px 12px 70px}}
  .column{{width:100%}}
  .arms{{gap:14px}}
}}
"""


_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>{css}</style></head>
<body>{topbar}<div class="canvas"><div class="column">{body}</div></div></body>
</html>"""


def render(spec: MockupSpec) -> str:
    return _Renderer(spec).render()
