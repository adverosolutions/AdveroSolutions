"""Markdown rendering for the verdict job (brief A7).

Pure string building. The job prints this to the terminal and writes it to
``.tmp/`` so the Friday audit (O6) can paste it straight into the retro
packet.

It is read on a Friday morning in a terminal, so the layout is built for
scanning: the verdict table carries numbers only, every reason is a bullet
under it, a section with nothing in it says so in one line instead of printing
an empty table, and every recommendation gets a next action rather than only
``retire``.
"""
import datetime
from typing import Any, Dict, List, Optional

from services.experiments import verdicts as V

# What Lorenzo does with each recommendation. Every recommendation in
# V.RECOMMENDATIONS needs a line here; the test pins that.
NEXT_ACTIONS = {
    "keep_running": "nothing to do. It is below the 1,000-send line, so no verdict is possible yet.",
    "run_to_3000": "leave the volume alone and let it reach 3,000 sends before deciding.",
    "scale": "give it the largest share of the 2026-10-11 inboxes. Raising a daily limit or moving "
             "an inbox is a live write, so stage it as a change-set.",
    "hold": "hold the current volume and fix the copy first. Do not add inboxes to it on Oct 11.",
    "rework_copy": "rewrite the offer sentence and the icebreaker, stage the new copy through "
                   "copy_validator.validate_copy, and give the rework its own 1,000 sends.",
    "retire": "this is a retirement proposal, not a retirement. Stage the pause and the email_list "
              "change as a change-set and let Lorenzo approve it.",
}


def _pct(value: float) -> str:
    return "%.2f%%" % (value * 100)


def _date(value) -> str:
    if value is None:
        return "not at this rate"
    if isinstance(value, datetime.date):
        return value.isoformat()
    return str(value)


def _row(cells: List[str]) -> str:
    return "| " + " | ".join(cells) + " |"


def _positives_cell(s) -> str:
    text = "%d (%s)" % (s.positives, _pct(s.positive_rate))
    closed = getattr(s, "closed_out", 0)
    if closed:
        text += " incl %d lost/no-show" % closed
    return text


def verdict_table(verdict_list: List[Any]) -> str:
    """Numbers only. The reason for each row is a bullet under the table: it
    runs to 180 characters and wraps the whole table when it sits in a cell."""
    if not verdict_list:
        return "No campaigns matched."
    head = ["Campaign", "Sends", "Real replies", "Positives", "Opportunities", "Recommendation",
            "Next point", "ETA now", "ETA at Oct 11 volume", "ETA blended"]
    lines = [_row(head), _row(["---"] * len(head))]
    for v in verdict_list:
        s = v.stats
        lines.append(_row([
            s.key,
            str(s.sent),
            "%d (%s)" % (s.real_replies, _pct(s.reply_rate)),
            _positives_cell(s),
            "%d / $%s" % (s.opportunities, "{:,}".format(s.opportunity_value)),
            v.recommendation,
            str(v.next_line) if v.next_line else "decided",
            _date(v.eta_current),
            _date(v.eta_oct11),
            _date(v.eta_blended),
        ]))
    return "\n".join(lines)


def reasons_block(verdict_list: List[Any]) -> str:
    if not verdict_list:
        return "No campaigns matched."
    return "\n".join(["- **%s** (%s): %s" % (v.stats.key, v.recommendation, v.reason)
                      for v in verdict_list])


def next_actions_block(verdict_list: List[Any]) -> str:
    """One action line per recommendation present, not only for retire."""
    if not verdict_list:
        return "No campaigns matched, so there is nothing to act on."
    seen = []  # type: List[str]
    for v in verdict_list:
        if v.recommendation not in seen:
            seen.append(v.recommendation)
    rows = []
    for rec in seen:
        keys = [v.stats.key for v in verdict_list if v.recommendation == rec]
        rows.append("- **%s** (%s): %s"
                    % (rec, ", ".join(keys), NEXT_ACTIONS.get(rec, "no action defined.")))
    return "\n".join(rows)


def flags_block(verdict_list: List[Any]) -> str:
    rows = []
    for v in verdict_list:
        for flag in v.flags:
            rows.append("- %s: %s" % (v.stats.key, flag))
    if not rows:
        return "No Section 6 threshold is breached."
    return "\n".join(rows)


def notes_block(verdict_list: List[Any]) -> str:
    rows = []
    for v in verdict_list:
        for note in getattr(v.stats, "notes", []) or []:
            rows.append("- %s: %s" % (v.stats.key, note))
    return "\n".join(rows)


def capacity_block(capacity: V.Capacity) -> str:
    line = ("Capacity: %d sends/day today (%d inboxes x %d), %d/day from %s (%d more inboxes finish "
            "warming), a %.2fx step." % (
                capacity.now_per_day, capacity.active_inboxes, capacity.per_inbox,
                capacity.after_step_per_day, V.CAPACITY_STEP_DATE.isoformat(),
                capacity.warming_inboxes, capacity.multiplier))
    notes = getattr(capacity, "notes", None) or []
    if not notes:
        return line
    return "\n".join([line, ""] + ["> WARNING: %s" % n for n in notes])


def variant_table(variant_verdicts: List[Any]) -> str:
    """Twelve rows of "nothing to compare" is not a table, it is a sentence."""
    if not variant_verdicts:
        return "No steps were judged."
    if all(vv.status == "single_variant" for vv in variant_verdicts):
        campaigns = sorted(set([vv.campaign for vv in variant_verdicts]))
        return ("All %d judged step(s) across %d campaign(s) are single-variant, so there is nothing "
                "to compare. The B variants are staged in changesets/instantly_phase0 and have not "
                "been applied." % (len(variant_verdicts), len(campaigns)))
    head = ["Campaign", "Step", "Status", "Winner", "Loser", "p", "Detail"]
    lines = [_row(head), _row(["---"] * len(head))]
    for vv in variant_verdicts:
        if vv.status == "single_variant":
            continue
        lines.append(_row([
            vv.campaign,
            str(vv.step),
            vv.status,
            vv.winner or "",
            vv.loser or "",
            "%.3f" % vv.p_value if vv.p_value is not None else "",
            vv.reason,
        ]))
    singles = len([vv for vv in variant_verdicts if vv.status == "single_variant"])
    if singles:
        lines.append("")
        lines.append("%d further step(s) are single-variant and have nothing to compare." % singles)
    return "\n".join(lines)


def experiment_table(doc: Dict[str, Any]) -> str:
    head = ["Id", "Campaigns", "Status", "Sample rule", "Current sample", "Winner", "Where it stands"]
    lines = [_row(head), _row(["---"] * len(head))]
    for exp in doc.get("experiments") or []:
        sample = exp.get("current_sample") or {}
        sample_text = ", ".join(["%s %s" % (k, sample[k]) for k in sorted(sample)]) or "none"
        if sample:
            sample_text += " (pooled across %d campaign(s))" % len(exp.get("campaigns") or [])
        result = exp.get("result") or {}
        gate = exp.get("sample_gate") or {}
        status = exp.get("status", "")
        if exp.get("post_decision") and status == "decided":
            status += " (frozen)"
        stands = result.get("reason") or exp.get("blocked_reason") or ""
        excluded = gate.get("excluded") or {}
        if excluded and not gate.get("undecidable"):
            # R12: say which campaigns the decision leaves out, and why.
            stands += "%sleft out of the decision: %s" % (
                ". " if stands else "",
                "; ".join("%s (%s)" % (k, excluded[k]) for k in sorted(excluded)))
        lines.append(_row([
            exp.get("id", ""),
            "%d campaigns" % len(exp.get("campaigns") or []),
            status,
            "%s %s" % (exp.get("sample_needed"), exp.get("sample_rule") or ""),
            sample_text,
            result.get("winner") or "",
            stands,
        ]))
    return "\n".join(lines)


def render(
    verdict_list: List[Any],
    variant_verdicts: List[Any],
    experiments_doc: Dict[str, Any],
    capacity: V.Capacity,
    as_of: datetime.date,
    mode: str,
    extra_notes: Optional[List[str]] = None,
) -> str:
    notes = notes_block(verdict_list)
    parts = [
        "# Campaign verdicts and experiments",
        "",
        "As of %s, MODE=%s. Read-only: this report calls Instantly analytics and the lead list "
        "and writes nothing to any live system." % (as_of.isoformat(), mode),
        "",
        capacity_block(capacity),
        "",
    ]
    for note in extra_notes or []:
        parts.extend(["> NOTE: %s" % note, ""])
    parts.extend([
        "## Verdicts",
        "",
        verdict_table(verdict_list),
        "",
        "### Why",
        "",
        reasons_block(verdict_list),
        "",
        "### Next action",
        "",
        next_actions_block(verdict_list),
        "",
        "ETA now holds today's rate forever. ETA at Oct 11 volume is the same line at the "
        "post-%s rate and is never earlier than %s, because that volume does not exist before "
        "then. ETA blended is the one to plan against: today's rate until %s, the higher rate "
        "after." % (V.CAPACITY_STEP_DATE.isoformat(), V.CAPACITY_STEP_DATE.isoformat(),
                    V.CAPACITY_STEP_DATE.isoformat()),
        "",
        "## Section 6 flags",
        "",
        flags_block(verdict_list),
        "",
    ])
    if notes:
        parts.extend(["## Data notes", "", notes, ""])
    parts.extend([
        "## Variants",
        "",
        variant_table(variant_verdicts),
        "",
        "## Experiments",
        "",
        experiment_table(experiments_doc),
        "",
    ])
    return "\n".join(parts)
