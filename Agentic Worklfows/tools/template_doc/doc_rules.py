"""Promises the one doc makes, in one place, so build.py (which writes them into
the doc), doc_areas.DocReader (which reads every template back out of the doc's
text) and record_doc_approvals.py (which must honour them) cannot drift.

Python 3.9, standard library only.
"""
import re
from collections import OrderedDict

# First replies to these question types are never approved from the doc (the
# doc says so on each of them). Every first reply is a draft Lorenzo sends
# himself (approval.py, FIRST_REPLY_LOCK_REASON); these were held back from
# "done" before that rule and still are.
HELD_QT = ("other", "referral")
HELD_NOTE = "Saying 'done' does not approve this one."


def is_held(template_id):
    """True for first_reply.<offer>.<held question type>.full."""
    parts = (template_id or "").split(".")
    return (len(parts) == 4 and parts[0] == "first_reply" and parts[3] == "full"
            and parts[2] in HELD_QT)


# Spliced lines: a cadence email "cadence.<name>" carries a placeholder that
# the engine fills with one of the lines "cadence.<name>.<family>.<key>".
# build.py derives hosts, families and placeholders from the catalogue and
# records each line's host as "spliced_into" in the manifest;
# record_doc_approvals.py reads the pairs from both builds' manifests and from
# splice_host on the catalogue's approvable ids. A line that is not approvable
# (cadence.e2.research_line) is shown as a read-only note on its email.
SPLICE_SECTION = "cadence"


def splice_host(template_id, approvable_ids):
    """The cadence email a spliced line belongs to, or None: the id's first
    two parts, when that is itself an approvable id and the id has more
    parts after it."""
    parts = (template_id or "").split(".")
    if len(parts) < 3 or parts[0] != SPLICE_SECTION:
        return None
    host = ".".join(parts[:2])
    return host if host in approvable_ids else None


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
# A follow-up email (the COMPANY_KEPT_SECTION) that names the company is held
# without one, so its missing_lead_data version keeps {company}; the top
# section says so with COMPANY_KEPT_CLAUSE whenever the catalogue has one.
GREETING = ("Hey {first_name},", "Hey there,")
COMPANY_FALLBACK = "your business"
COMPANY_KEPT_SECTION = "cadence"
COMPANY_KEPT_CLAUSE = "A follow-up email that names the company is held until we have it."
REFERRAL_FALLBACKS = (("{referral_name}", "the right person"), ("{referral_first_name}", "them"))


def missing_data_sentence(company_kept):
    """The top section's paragraph on missing lead data. company_kept: the
    follow-up emails keep {company} (and are held without it)."""
    return ("If we don't have their first name, '%s' becomes '%s'. If we don't have their company name, "
            "{company} becomes '%s'.%s In a referral reply with no name, %s becomes '%s' and %s becomes '%s'."
            % (GREETING[0], GREETING[1], COMPANY_FALLBACK, (" " + COMPANY_KEPT_CLAUSE) if company_kept else "",
               REFERRAL_FALLBACKS[0][0], REFERRAL_FALLBACKS[0][1], REFERRAL_FALLBACKS[1][0],
               REFERRAL_FALLBACKS[1][1]))


def company_for(template_id, company, company_kept):
    """What {company} becomes in this template's missing_lead_data version,
    as the top section states it."""
    return "{company}" if company_kept and section_of(template_id) == COMPANY_KEPT_SECTION else company


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
# Shown in full after WHOLE_NOTE instead: the dated and other-timezone
# versions that write out example times (Lorenzo, 2026-09-23: "the 25
# time/timezone versions shown in full"), and any version whose changes these
# forms cannot say exactly (a line moved into another paragraph, say).
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
WHOLE_NOTE = "This version in full:"
# A version that is exactly two other versions together is shown as one note.
COMBOS = OrderedDict([
    ("no_call_link_or_loom", (("no_call_link", "no_loom_url"),
                              "Both changes above apply: the one for no call link and the one for no Loom link.")),
])
EXAMPLE_TIMES_NOTE = "The times in this version are examples."
TIME_VALUE_RE = re.compile(r"\b\d{1,2}(?::\d\d)?[ap]m\b")
# The follow-up emails whose versions write a spliced line out in full: the
# doc says which line and which versions (the one for missing details, which
# the top section explains, and the versions shown below), and DocReader puts
# it back where the placeholder is.
PIN_NOTE = 'In %s, %s is written out as "%s"'
PIN_SCOPE_MISSING = "the version for when we don't have their details (see the top of this doc)"
PIN_SCOPE_SHOWN = "the versions below"
PIN_RE = re.compile(r'^In (.+?), (\{[A-Za-z_][A-Za-z0-9_]*\}) is written out as "(.*)"$')
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
