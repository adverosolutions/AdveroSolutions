"""Promises the one doc makes, in one place, so build.py (which writes them into
the doc) and record_doc_approvals.py (which must honour them) cannot drift.

Python 3.9, standard library only.
"""
from collections import OrderedDict

# First replies to these question types "start as an approval card to you
# until you say otherwise" (the doc says so on each of them). Saying "done"
# on the doc is not "otherwise": they are never approved from the doc.
HELD_QT = ("other", "referral")
HELD_NOTE = "Starts as an approval card to you until you say otherwise."


def is_held(template_id):
    """True for first_reply.<offer>.<held question type>.full."""
    parts = (template_id or "").split(".")
    return (len(parts) == 4 and parts[0] == "first_reply" and parts[3] == "full"
            and parts[2] in HELD_QT)


# Lines build_touch splices into a cadence day: host id -> [(fragment id, heading)].
SPLICED = OrderedDict([
    ("cadence.d2", [
        ("cadence.d2.research_fallback.reactivation", "Reactivation offers (line used inside Day 2)"),
        ("cadence.d2.research_fallback.outbound", "Outbound offers (line used inside Day 2)"),
    ]),
    ("cadence.d4", [
        ("cadence.d4.case_study.reactivation", "Reactivation offers (line used inside Day 4)"),
        ("cadence.d4.case_study.outbound", "Outbound offers (line used inside Day 4)"),
    ]),
    ("cadence.d5", [
        ("cadence.d5.free_work.cleaning_reactivation", "Cleaning, reactivation (line used inside Day 5)"),
        ("cadence.d5.free_work.cleaning_outbound", "Cleaning, outbound (line used inside Day 5)"),
        ("cadence.d5.free_work.bookkeeping_reactivation", "Bookkeeping, reactivation (line used inside Day 5)"),
        ("cadence.d5.free_work.bookkeeping_outbound", "Bookkeeping, outbound (line used inside Day 5)"),
        ("cadence.d5.free_work.recruiting_reactivation", "Recruiting, reactivation (line used inside Day 5)"),
        ("cadence.d5.free_work.recruiting_outbound", "Recruiting, outbound, specialty unknown (line used inside Day 5)"),
        ("cadence.d5.free_work.recruiting_outbound_specialty", "Recruiting, outbound, specialty known (line used inside Day 5)"),
        ("cadence.d5.free_work.generic_reactivation", "Any other niche, reactivation (line used inside Day 5)"),
        ("cadence.d5.free_work.generic_outbound", "Any other niche, outbound (line used inside Day 5)"),
    ]),
])


def splice_pairs():
    """[(host id, fragment id)]"""
    return [(host, fid) for host, frs in SPLICED.items() for fid, _ in frs]


# The doc's top-level sections that hold engine emails, by id prefix.
ENGINE_SECTIONS = ("first_reply", "cadence", "booking", "show_rate", "no_show")


def section_of(tag):
    """The engine section a tag belongs to, or None (Instantly, Upwork, the
    build line, the time formats, the closing notes)."""
    head = (tag or "").split(".", 1)[0].split("/", 1)[0]
    return head if head in ENGINE_SECTIONS else None
