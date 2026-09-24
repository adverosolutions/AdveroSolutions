"""Promises the one doc makes, in one place, so build.py (which writes them into
the doc), doc_areas.DocReader (which reads every template back out of the doc's
text) and record_doc_approvals.py (which must honour them) cannot drift.

Python 3.9, standard library only.
"""
import re
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


# ------------------------------------------------------------ the hash's text
def normalise(text):
    """services/reply_engine/template_approvals.normalise, the normalisation
    every template hash is taken over (line ends unified, trailing spaces
    dropped, runs of blank lines collapsed to one, ends stripped). Copied so
    build.py needs no engine import; tests/test_doc_variants.py checks that
    the two agree."""
    lines = [ln.rstrip() for ln in (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def norm_lines(lines):
    """A list of lines as the hash sees them: normalise() split into lines."""
    t = normalise("\n".join(lines))
    return t.split("\n") if t else []


# -------------------------------------------- missing lead data (top section)
# The top section says how a missing first name, company or referral name is
# written. build.py writes these sentences from the values below; a
# missing_lead_data version that is exactly these substitutions of the main
# text is not shown again, and doc_areas.DocReader rebuilds it from the
# sentences as the doc prints them (so the doc, not this file, is what counts).
GREETING = ("Hey {first_name},", "Hey there,")
COMPANY_FALLBACK = "your business"
COMPANY_FALLBACK_TEAM = "your team"
TEAM_DAYS = ("2", "4", "5", "30")  # cadence days whose missing-data version says 'your team'
REFERRAL_FALLBACKS = (("{referral_name}", "the right person"), ("{referral_first_name}", "them"))


def team_ids():
    return ["cadence.d%s" % d for d in TEAM_DAYS]


def day_list(days):
    """('2', '4', '5', '30') -> '2, 4, 5 and 30'"""
    days = list(days)
    return days[0] if len(days) == 1 else "%s and %s" % (", ".join(days[:-1]), days[-1])


def missing_data_sentence():
    return ("If we don't have their first name, '%s' becomes '%s'. If we don't have their company name, "
            "{company} becomes '%s' ('%s' in the Day %s follow-ups). In a referral reply with no name, "
            "%s becomes '%s' and %s becomes '%s'."
            % (GREETING[0], GREETING[1], COMPANY_FALLBACK, COMPANY_FALLBACK_TEAM, day_list(TEAM_DAYS),
               REFERRAL_FALLBACKS[0][0], REFERRAL_FALLBACKS[0][1], REFERRAL_FALLBACKS[1][0],
               REFERRAL_FALLBACKS[1][1]))


def fill_missing(lines, greeting, company, referrals):
    """The main text with the missing-data fallbacks put in, line by line, in
    the order the top section gives them."""
    out = []
    for ln in lines:
        ln = ln.replace(greeting[0], greeting[1]).replace("{company}", company)
        for ph, fb in referrals:
            ln = ln.replace(ph, fb)
        out.append(ln)
    return out


# ------------------------------------------------------------- subjects
# A subject variant is the "Subject:" line plus fallback lines; the doc shows
# the fallbacks in one grey note after the Subject line, in the same order.
SUBJECT_PREFIX = "Subject: "
SUBJECT_FALLBACKS = (
    ("Subject when the thread has none: ", "If their email had no subject: "),
    ("Subject when there is no first name either: ", "If we also don't have their first name: "),
)


def subject_note(fallback_lines):
    """The grey note for a subject variant's fallback lines (export form)."""
    parts = []
    for ln in fallback_lines:
        for export_prefix, doc_prefix in SUBJECT_FALLBACKS:
            if ln.startswith(export_prefix):
                parts.append(doc_prefix + ln[len(export_prefix):] + ".")
                break
        else:
            raise ValueError("unknown subject line %r" % ln)
    return " ".join(parts)


def read_subject_note(note):
    """Export-form fallback lines from a subject note, or None if the note is
    not exactly what subject_note() writes for some lines."""
    doc_prefixes = [d for _, d in SUBJECT_FALLBACKS]
    pieces = re.split("(%s)" % "|".join(re.escape(d) for d in doc_prefixes), note)
    if len(pieces) < 3 or pieces[0] != "":
        return None
    out = []
    for i in range(1, len(pieces), 2):
        value = pieces[i + 1]
        end = "." if i + 2 >= len(pieces) else ". "
        if not value.endswith(end):
            return None
        export_prefix = next(e for e, d in SUBJECT_FALLBACKS if d == pieces[i])
        out.append(export_prefix + value[:-len(end)])
    try:
        if subject_note(out) != note:
            return None
    except ValueError:
        return None
    return out


# -------------------------------------------------------------- variants
# A variant is shown as the changes it makes to the email's main text. Its
# block starts with its label ("If there are no free times:"), then any
# informational notes, then one grey note per change, each followed by the
# lines that change puts in (those lines are the block's text):
#
#   Instead of "A" and "B":          A and B (consecutive lines of the main
#                                    text, with the blank lines between them)
#                                    are replaced by the lines that follow
#   Leaves out "A".                  A is dropped (and a paragraph break with it
#                                    when A was a paragraph of its own)
#   Adds after "X":                  the lines that follow go right after X,
#                                    in X's paragraph
#   Adds a new paragraph after "X":  the same, as a new paragraph
#   Adds before "Y":                 right before Y, in Y's paragraph
#   Adds at the start:               before the first line, in its paragraph
#   Adds a new paragraph at the start:
#
# Quoted lines are whole lines of the main text, character for character, in
# order; a change is always further down than the one before it. So each
# version's full text follows from the doc alone (doc_areas.DocReader does
# exactly that, and build.py refuses to write a doc it cannot read back).
CHANGE_FORMS = OrderedDict([
    ("instead", "Instead of %s:"),
    ("leaves", "Leaves out %s."),
    ("after", "Adds after %s:"),
    ("after_para", "Adds a new paragraph after %s:"),
    ("before", "Adds before %s:"),
    ("start", "Adds at the start:"),
    ("start_para", "Adds a new paragraph at the start:"),
])
QUOTING = ("instead", "leaves")          # quote one or more consecutive lines
ANCHORED = ("after", "after_para", "before")  # quote exactly one line
SAME_AS_MAIN = "Same words as the email above."
# A version that is exactly two other versions together is shown as one note.
COMBOS = OrderedDict([
    ("no_call_link_or_loom", (("no_call_link", "no_loom_url"),
                              "Both changes above apply: the one for no call link and the one for no Loom link.")),
])
EXAMPLE_TIMES_NOTE = "The times in this version are examples."
TIME_VALUE_RE = re.compile(r"\b\d{1,2}(?::\d\d)?[ap]m\b")
# The cadence days whose versions write a spliced line out in full: the doc
# says which line, and DocReader puts it back where the placeholder is.
PIN_NOTE = 'In the versions below, %s is written out as "%s"'
PIN_RE = re.compile(r'^In the versions below, (\{[A-Za-z_][A-Za-z0-9_]*\}) is written out as "(.*)"$')
# More than one distinct time-formats text: each email says which it uses.
VF_VERSION_NOTE = "Times in this email are written as in version %d of the time formats at the top."
VF_VERSION_RE = re.compile(r"^Times in this email are written as in version (\d+) of the time formats at the top\.$")


def quote_list(lines):
    """'"A"', '"A" and "B"', '"A", "B" and "C"'."""
    qs = ['"%s"' % l for l in lines]
    return qs[0] if len(qs) == 1 else "%s and %s" % (", ".join(qs[:-1]), qs[-1])


def change_note(kind, quoted):
    form = CHANGE_FORMS[kind]
    if kind in QUOTING or kind in ANCHORED:
        return form % quote_list(quoted)
    return form


def change_kind(note):
    """The change kind a note line starts, or None for any other note. The
    quoted lines are matched against the text by doc_areas.DocReader."""
    for kind, form in CHANGE_FORMS.items():
        if "%s" not in form:
            if note == form:
                return kind
            continue
        head, tail = form.split("%s")
        if note.startswith(head + '"') and note.endswith('"' + tail) and len(note) > len(head) + len(tail) + 1:
            return kind
    return None
