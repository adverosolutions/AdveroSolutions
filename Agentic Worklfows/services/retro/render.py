"""Markdown rendering shared by the Friday retro (A10) and the client scorecard (A12).

Both outputs are the same shape: a title, a dated subtitle, a list of sections,
and a list of caveats. Building one is choosing which sections to put in it;
rendering is this module's job and nothing else's. A12 should import
``Packet``/``Section``/``metric_table``/``render_markdown`` and
``scorecard.build_client_scorecard`` rather than writing its own renderer.

Copy rules (config/offers.md, rule 8) apply to anything a client could read, so
``check_client_copy`` is run over the rendered scorecard before it is returned:
no em dashes, no exclamation marks, no mention of AI or automation, signed
"Lorenzo". The internal retro is exempt, because it is Lorenzo talking to
himself about the machine.
"""
import re
from typing import Any, Dict, List, Optional

EM_DASH = "—"
EN_DASH = "–"

# Words a client-facing document must not contain. Rule 8 of the offer sheet
# ("never mention AI, automation tools, or that a system wrote the email")
# applied to the scorecard, which is the one artefact from this package that
# leaves the building.
BANNED_CLIENT_WORDS = (
    "ai", "a.i.", "artificial intelligence", "automation", "automated", "automate",
    "bot", "chatbot", "llm", "gpt", "claude", "openai", "anthropic", "script",
    "algorithm", "machine learning", "robot",
)

NOT_AVAILABLE = "not available"


class Section(object):
    """One block of the packet. Any combination of prose, bullets and a table."""

    def __init__(self, heading, body=None, bullets=None, table=None, note=None):
        # type: (str, Optional[str], Optional[List[str]], Optional[Dict[str, Any]], Optional[str]) -> None
        self.heading = heading
        self.body = body
        self.bullets = bullets or []
        self.table = table
        self.note = note

    def as_dict(self):
        return {
            "heading": self.heading, "body": self.body, "bullets": list(self.bullets),
            "table": self.table, "note": self.note,
        }


CAVEATS_HEADING = "Read this before you trust a number"


class Packet(object):
    def __init__(self, title, subtitle="", sections=None, caveats=None, meta=None,
                 caveats_heading=CAVEATS_HEADING):
        # type: (str, str, Optional[List[Section]], Optional[List[str]], Optional[Dict[str, Any]], str) -> None
        self.title = title
        self.subtitle = subtitle
        self.sections = sections or []
        self.caveats = caveats or []
        self.meta = meta or {}
        self.caveats_heading = caveats_heading or CAVEATS_HEADING

    def as_dict(self):
        return {
            "title": self.title, "subtitle": self.subtitle,
            "sections": [s.as_dict() for s in self.sections],
            "caveats": list(self.caveats), "meta": dict(self.meta),
            "caveats_heading": self.caveats_heading,
        }


def table(columns, rows):
    # type: (List[str], List[List[Any]]) -> Dict[str, Any]
    return {"columns": list(columns), "rows": [list(r) for r in rows]}


# --------------------------------------------------------------- formatting
def fmt_number(value, unit=""):
    # type: (Any, str) -> str
    """A number the way the packet prints it, or the honest absence of one."""
    if value is None:
        return NOT_AVAILABLE
    if unit == "%":
        # Rates are ALWAYS stored as fractions (0.0122 = 1.22%). Guessing from
        # the magnitude would render a real 100% rate as 1.00%.
        return "%.2f%%" % (float(value) * 100.0)
    if unit == "$":
        return "$%s" % format(int(round(float(value))), ",d")
    if isinstance(value, float):
        if abs(value - round(value)) < 1e-9:
            return str(int(round(value)))
        return "%.2f" % value
    return str(value)


def fmt_delta(this_value, last_value, unit=""):
    # type: (Any, Any, str) -> str
    """"+3" / "-0.40pp" / "new" / "not available". Never invents a direction."""
    if this_value is None or last_value is None:
        return NOT_AVAILABLE
    try:
        a = float(this_value)
        b = float(last_value)
    except (TypeError, ValueError):
        return NOT_AVAILABLE
    diff = a - b
    if diff == 0:
        # Same number, whether both are zero or both are 300. "+0" reads as a
        # change and sends the eye looking for one.
        return "flat"
    if unit == "%":
        # A percentage-point difference is defined even when last week was zero,
        # so a rate never degrades to "new".
        return "%+.2fpp" % (diff * 100.0)
    if b == 0:
        return "new"
    if unit == "$":
        sign = "+" if diff >= 0 else "-"
        return sign + fmt_number(abs(diff), "$")
    if abs(diff - round(diff)) < 1e-9:
        return "%+d" % int(round(diff))
    return "%+.2f" % diff


def metric_table(metrics, this_label="This week", last_label="Last week", include_source=True):
    # type: (List[Any], str, str, bool) -> Dict[str, Any]
    """The funnel table both outputs use. ``metrics`` are metrics.Metric objects."""
    columns = ["Metric", this_label, last_label, "Change"]
    if include_source:
        columns.append("Source")
    rows = []
    for m in metrics:
        row = [
            m.label,
            fmt_number(m.this_week, m.unit),
            fmt_number(m.last_week, m.unit),
            fmt_delta(m.this_week, m.last_week, m.unit),
        ]
        if include_source:
            # The note qualifies the number, so it has to be visible when the
            # number is there. Showing it only in place of a missing value hid
            # "GHL appointment status is the better source once a token exists"
            # from every packet that had a value for Calls held, which is every
            # packet.
            if m.this_week is None:
                row.append(m.note or "no source")
            elif m.note:
                row.append("%s (%s)" % (m.source, m.note) if m.source else m.note)
            else:
                row.append(m.source)
        rows.append(row)
    return table(columns, rows)


def render_table(spec):
    # type: (Dict[str, Any]) -> str
    columns = [str(c) for c in spec.get("columns") or []]
    rows = spec.get("rows") or []
    if not columns:
        return ""
    lines = ["| " + " | ".join(columns) + " |",
             "| " + " | ".join("---" for _ in columns) + " |"]
    for row in rows:
        cells = [("" if c is None else str(c)).replace("|", "\\|") for c in row]
        while len(cells) < len(columns):
            cells.append("")
        lines.append("| " + " | ".join(cells[:len(columns)]) + " |")
    return "\n".join(lines)


def render_markdown(packet):
    # type: (Packet) -> str
    out = ["# %s" % packet.title]
    if packet.subtitle:
        out.append("")
        out.append(packet.subtitle)
    for section in packet.sections:
        out.append("")
        if section.heading:
            out.append("## %s" % section.heading)
        if section.body:
            out.append("")
            out.append(section.body.rstrip())
        if section.table:
            out.append("")
            out.append(render_table(section.table))
        if section.bullets:
            out.append("")
            for bullet in section.bullets:
                out.append("- %s" % bullet)
        if section.note:
            out.append("")
            out.append("> %s" % section.note)
    if packet.caveats:
        out.append("")
        out.append("## %s" % getattr(packet, "caveats_heading", CAVEATS_HEADING))
        out.append("")
        for caveat in packet.caveats:
            out.append("- %s" % caveat)
    out.append("")
    return "\n".join(out)


# ------------------------------------------------------------- copy guard
def check_copy(text, ban_words=True, require_signature=True):
    # type: (str, bool, bool) -> List[str]
    """Violations of the offer-sheet copy rules. Empty list means clean.

    ``ban_words=False`` keeps the punctuation and signature rules but drops the
    AI/automation word ban. That is the setting for the Maker School post: the
    ban exists to keep those words out of prospect email, and a community of
    people building automations is not prospect email.
    """
    problems = []
    if EM_DASH in text:
        problems.append("contains an em dash")
    if "!" in text:
        problems.append("contains an exclamation mark")
    lowered = text.lower()
    if ban_words:
        for word in BANNED_CLIENT_WORDS:
            # Word-boundary match so "aim", "domain" and "description" are not hits.
            if re.search(r"(?<![a-z])%s(?![a-z])" % re.escape(word), lowered):
                problems.append("mentions %r" % word)
    if require_signature and "lorenzo" not in lowered:
        problems.append("is not signed Lorenzo")
    return problems


def check_client_copy(text):
    # type: (str) -> List[str]
    """The strict rules, for anything a client or prospect could read.

    ``scorecard`` raises on these: a scorecard that says "automation" in front
    of a client is worse than no scorecard.
    """
    return check_copy(text, ban_words=True, require_signature=True)


class ClientCopyError(Exception):
    pass


def require_client_copy(text):
    # type: (str) -> str
    problems = check_client_copy(text)
    if problems:
        raise ClientCopyError(
            "client-facing copy breaks the offer-sheet rules: %s" % "; ".join(problems)
        )
    return text
