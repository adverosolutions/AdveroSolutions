"""``validate_copy()`` - the copy gate the change-sets use, extended (brief A7).

The Phase 0 change-set already validates its staged sequences with
``changesets.instantly_phase0.phase0_lib.validate_sequence``. This module is
the same gate plus the checks A7 adds, so a change-set switches one import
and keeps everything it already had:

    from services.experiments.copy_validator import validate_copy
    report = validate_copy(key, sequence_doc, live_campaign, settings_doc, OFFERS_MD)
    if not report.ok:
        raise SystemExit(report.summary())

**Wired in.** ``changesets/instantly_phase0/apply_instantly_phase0.py``
imports ``validate_copy`` (line 63) and calls it with its defaults for every
campaign it applies (line 214), so the checks below run on the only code path
that can PATCH a live campaign: rules 1 and 2 as errors, the top-level spin
count, the readability rule and unknown new variables as warnings. The strict
options (``strict_readability=True``, ``require_known_vars=True``) are not
passed there; pass them when checking new copy by hand.

Inherited from phase0_lib (not re-implemented here): the three-step shape and
thread rules (step 1 opens with ``{{personalization}}`` on its own line, step 2
keeps an empty subject, step 3 a fresh one), exactly variants A and B on step 1,
balanced spintax braces, 3 to 5 spin points per email counting nested ones,
spin options that are at least two, non-empty and not repeated, a bare
option that is one of the campaign's variable names, every merge variable
present in the campaign's variable list, the known typos, one proof point per campaign
matching config/offers.md, no em or en dash, no exclamation mark, no dollar
figure or time window that is not in the campaign's offers.md row, no
guarantee language on a reactivation offer, no AI or automation, signed
Lorenzo, A/B variants that are not byte-identical.

Added here, in ``validate_copy``:

1. **A merge variable anywhere inside a spin option** (error). phase0_lib
   does not catch this shape. Its option check is
   ``VAR_NAME_RE.match(o) and o in known_vars | new_vars``,
   and ``VAR_NAME_RE`` is ``^[A-Za-z_][A-Za-z0-9_]*$``. It errors on a bare
   option such as ``firstName`` only when that name is one of the campaign's
   variables (the live campaign's variable list or the settings doc's
   ``new_variables``), and it never matches the string ``{{firstName}}``, so even
   the crude ``{{RANDOM | {{firstName}} | there}}`` passes it (verified against
   phase0_lib on 2026-09-22). The shape that actually reaches inboxes is
   ``{{RANDOM | Hey {{firstName}} | Hi {{firstName}}}}``: Instantly renders the
   spin first, and a variable inside a chosen option is the documented
   "preview before launch" trap in M3.2 ("never the merge variables"). Any
   variable nested in a spin is an error here, and this rule is the only guard
   there is.
2. **One proof family per campaign, and the right one** (errors). phase0_lib
   checks each variant against its own offer type. This checks the campaign as
   a whole: reactivation copy and outbound copy must never appear in the same
   campaign, whatever step they sit on, and the family the copy carries must
   be the campaign's ``offer`` in the settings doc.
3. **Readability.** A sentence over 30 words is flagged. It is a *warning* by
   default, on purpose: 15 sentences in the already-staged Phase 0 copy are
   over 30 words in their longest rendering, and a validator that turns a
   Phase 0 apply red on a style rule would just be switched off. Pass
   ``strict_readability=True`` to make it an error for new copy.
4. **New-variable strictness.** phase0_lib warns when copy uses a variable
   listed in ``new_variables`` but not yet on the live campaign. Pass
   ``require_known_vars=True`` (what the list factory should do once the leads
   carry the field) to make that an error.

Also a warning, not a rule of its own: the spin count without the nested
spins, when it falls outside phase0_lib's 3 to 5 (phase0_lib counts nested
ones too).

Every sentence measured on the **longest** rendering of the spintax: the
worst case is the one that lands in an inbox one time in three.

``validate_email()`` is the single-email subset, for copy checked by hand with
no campaign or offer sheet: spintax parses, 3 to 5 spin points, at least two
options and no repeated option per spin, no variable inside a spin, every
variable in ``known_variables`` when that is given, no em or en dash, no
exclamation mark, no AI or automation, signed Lorenzo (all errors), and
sentences over the word limit (warnings).
"""
import re
from typing import Any, Dict, Iterable, List, Optional, Set

from changesets.instantly_phase0 import phase0_lib as p0

MAX_SENTENCE_WORDS = 30

# Sentence break: . ? ! followed by whitespace or end, or any newline. Bullets
# and the greeting line are their own sentences because of the newline rule.
_SENTENCE_SPLIT = re.compile(r"(?:[.?!]+[\s]+|[.?!]+$|\n+)")
# "$1.5k", "2,500", "3.5" must not split a sentence: the decimal point is
# swapped for a sentinel while the text is split, then put back.
_DECIMAL = re.compile(r"(\d)\.(\d)")
_SENTINEL = chr(0)

Report = p0.Report
TagError = p0.TagError


# ---------------------------------------------------------------- rendering
def render(text: str, mode: str = "longest") -> str:
    """Render spintax to one concrete string.

    mode "first"    the first option of every spin (what a preview shows)
    mode "longest"  the option with the most words (the worst case for
                    readability)
    mode "shortest" the option with the fewest words

    Non-RANDOM tags become a single placeholder word, because a merge variable
    contributes one word to a sentence however long the value is.
    """
    out = []
    i = 0
    n = len(text)
    while i < n:
        if text.startswith("{{", i):
            tags = p0.find_tags(text[i:])
            if not tags:
                out.append(text[i])
                i += 1
                continue
            _s, end, inner = tags[0]
            head = inner.strip().split("|", 1)[0].strip()
            if head.upper() == "RANDOM":
                options = [o.strip() for o in p0._split_top_level(inner)[1:]]
                options = [o for o in options if o != ""] or [""]
                rendered = [render(o, mode) for o in options]
                if mode == "first":
                    pick = rendered[0]
                elif mode == "shortest":
                    pick = min(rendered, key=lambda s: len(s.split()))
                else:
                    pick = max(rendered, key=lambda s: len(s.split()))
                out.append(pick)
            else:
                out.append("X")
            i += end
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def sentences(text: str) -> List[str]:
    guarded = _DECIMAL.sub("\\1" + _SENTINEL + "\\2", text)
    parts = [s.strip() for s in _SENTENCE_SPLIT.split(guarded)]
    return [s.replace(_SENTINEL, ".") for s in parts if s.strip()]


def long_sentences(text: str, max_words: int = MAX_SENTENCE_WORDS, mode: str = "longest") -> List[str]:
    """Sentences over ``max_words`` in the given rendering of ``text``."""
    return [s for s in sentences(render(text, mode)) if len(s.split()) > max_words]


# ----------------------------------------------------------- extended rules
def variables_inside_spins(text: str) -> List[str]:
    """Every merge variable that sits inside a spin option, at any depth.

    ``{{RANDOM | Hey {{firstName}} | Hi {{firstName}}}}`` yields
    ``['{{firstName}} inside {{RANDOM | Hey {{firstName}} ...']``.
    """
    found = []
    for raw, options in p0.iter_spins(text):
        for option in options:
            for name in sorted(p0.merge_variables(option)):
                found.append("{{%s}} inside %s" % (name, raw[:50]))
    return found


def top_level_spin_count(text: str) -> int:
    """Spin points that are not nested inside another spin."""
    count = 0
    for _s, _e, inner in p0.find_tags(text):
        head = inner.strip().split("|", 1)[0].strip()
        if head.upper() == "RANDOM":
            count += 1
    return count


def _distinguishing_markers() -> Dict[str, List[str]]:
    """Per offer family, the ``OFFER_MARKERS`` strings that only it carries.

    Derived, not copied: the reactivation and outbound proof lines share
    "$150M" (the roofer's revenue), so the shared markers are dropped and what
    is left is what tells the two families apart. If offers.md and
    ``OFFER_MARKERS`` move together - the reactivation figure goes from $6M to
    $7.2M, say - these rules follow instead of silently going quiet.
    """
    families = {f: set(m.get("must") or []) for f, m in p0.OFFER_MARKERS.items()}
    shared = set()
    for family, markers in families.items():
        for other, other_markers in families.items():
            if other != family:
                shared |= markers & other_markers
    out = {}
    for family, markers in families.items():
        distinguishing = sorted(markers - shared)
        for marker in list(distinguishing):
            distinguishing.extend([a for a in MARKER_ALIASES.get(marker, ()) if a not in distinguishing])
        out[family] = distinguishing
    return out


# Spellings of a marker that mean the same number. "$180" already matches
# "$180K" and "$180,000" by prefix; the bare forms do not.
MARKER_ALIASES = {
    "$6M": ("$6 million", "$6,000,000", "6,000,000", "6 million"),
    "$180": ("$180K", "$180,000", "180,000", "180K"),
    "$150M": ("$150 million", "$150,000,000"),
}

def assert_distinguishable(markers: Dict[str, List[str]]) -> Dict[str, List[str]]:
    """A family with no distinguishing marker would make both campaign-level
    proof rules pass for ever without anyone noticing. Fail loudly instead."""
    for family, found in sorted(markers.items()):
        if not found:
            raise RuntimeError(
                "offer family %r has no marker that distinguishes it from the others in "
                "phase0_lib.OFFER_MARKERS, so the campaign-level proof rules would never fire. "
                "Fix OFFER_MARKERS (or config/offers.md) before using this validator." % family)
    return markers


PROOF_MARKERS = assert_distinguishable(_distinguishing_markers())


def proof_families(text: str) -> Set[str]:
    """Which offer type's proof numbers appear in this text.

    Derived from ``phase0_lib.OFFER_MARKERS`` (plus alternative spellings of
    the same figure), so the two definitions cannot drift: the reactivation
    claim is "$6M ... 6 months" and the outbound claim is "$180 ... 90 days",
    both on top of the shared "$150M/year" roofer, and the shared part is
    exactly what is excluded here.
    """
    out = set()
    for family, markers in PROOF_MARKERS.items():
        if any(marker in text for marker in markers):
            out.add(family)
    return out


def _campaign_text(sequence_doc: Dict[str, Any]) -> List[Any]:
    """[(label, subject + body text)] for every variant in the doc."""
    rows = []
    for si, vi, _step, var in p0.iter_variants(sequence_doc):
        label = "step%d/variant%s" % (si + 1, "AB"[vi] if vi < 2 else str(vi))
        subject = var.get("subject") or ""
        body = p0.html_to_text(var.get("body") or "")
        rows.append((label, subject + "\n" + body))
    return rows


# ------------------------------------------------------------- entry points
def validate_copy(
    campaign_key: str,
    sequence_doc: Dict[str, Any],
    live_campaign: Dict[str, Any],
    settings_doc: Dict[str, Any],
    offers_md: str,
    max_sentence_words: int = MAX_SENTENCE_WORDS,
    strict_readability: bool = False,
    require_known_vars: bool = False,
) -> Report:
    """The Phase 0 gate plus the A7 rules. Returns a phase0_lib.Report, so
    ``.ok``, ``.errors``, ``.warnings`` and ``.summary()`` behave exactly as
    the change-sets already expect."""
    rep = p0.validate_sequence(campaign_key, sequence_doc, live_campaign, settings_doc, offers_md)

    if require_known_vars:
        promoted = [w for w in rep.warnings if "is NEW for this campaign" in w]
        for warning in promoted:
            rep.warnings.remove(warning)
            rep.errors.append(warning.replace("is NEW for this campaign", "is NOT on the live campaign"))

    families = set()
    for label, text in _campaign_text(sequence_doc):
        # 1. merge variables inside spins
        try:
            nested = variables_inside_spins(text)
        except TagError as exc:
            # validate_sequence already recorded the brace error for this
            # variant; do not double-report it, and do not crash.
            rep.warn(label, "spintax could not be parsed for the extended checks: %s" % exc)
            continue
        for item in nested:
            rep.error(label, "merge variable inside a spin option (Instantly renders the spin "
                             "first, so this is the preview trap M3.2 warns about): %s" % item)

        # 2. spin count, counted without the nested ones
        top = top_level_spin_count(text)
        if not (p0.MIN_SPINS <= top <= p0.MAX_SPINS):
            rep.warn(label, "%d top-level spin points (%d-%d wanted); the total including nested "
                            "spins is what phase0_lib counts" % (top, p0.MIN_SPINS, p0.MAX_SPINS))

        # 3. readability
        for sentence in long_sentences(text, max_sentence_words):
            words = len(sentence.split())
            message = "sentence runs %d words in its longest rendering (limit %d): %r" % (
                words, max_sentence_words, sentence[:90])
            if strict_readability:
                rep.error(label, message)
            else:
                rep.warn(label, message)

        families |= proof_families(text)

    # 4. one proof family per campaign
    if len(families) > 1:
        rep.error(
            "campaign",
            "two proof families in one campaign (%s). config/offers.md allows one proof point per "
            "campaign: the roofer is $6M in 6 months in reactivation copy and $180K in 90 days in "
            "outbound copy, never both" % ", ".join(sorted(families)),
        )
    cfg = (settings_doc.get("campaigns") or {}).get(campaign_key) or {}
    offer = cfg.get("offer")
    if families and offer and families != set([offer]):
        rep.error(
            "campaign",
            "campaign offer is %r but the copy carries %s proof" % (offer, ", ".join(sorted(families))),
        )
    return rep


def validate_email(
    subject: str,
    body_text: str,
    known_variables: Optional[Iterable[str]] = None,
    max_sentence_words: int = MAX_SENTENCE_WORDS,
    label: str = "email",
) -> Report:
    """The rules that apply to a single email, with no campaign or offer sheet
    in hand. Used for ad-hoc copy checks (a new step, a subsequence body, a
    draft pasted into the runbook); the campaign-level rules need
    ``validate_copy``."""
    rep = Report(label)
    known = set(known_variables or [])
    text = (subject or "") + "\n" + (body_text or "")
    try:
        spins = list(p0.iter_spins(text))
    except TagError as exc:
        rep.error(label, "spintax/tag error: %s" % exc)
        return rep
    if not (p0.MIN_SPINS <= len(spins) <= p0.MAX_SPINS):
        rep.error(label, "%d spin points; need %d-%d" % (len(spins), p0.MIN_SPINS, p0.MAX_SPINS))
    for raw, options in spins:
        if len(options) < 2:
            rep.error(label, "spin needs >=2 options: %s" % raw[:60])
        if len(set(options)) != len(options):
            rep.error(label, "spin repeats an option: %s" % raw[:60])
    for item in variables_inside_spins(text):
        rep.error(label, "merge variable inside a spin option: %s" % item)
    if known:
        for name in sorted(p0.merge_variables(text)):
            if name not in known:
                rep.error(label, "{{%s}} not in %s" % (name, sorted(known)))
    for dash in p0.DASHES:
        if dash in text:
            rep.error(label, "contains %s dash" % ("em" if dash == p0.EM_DASH else "en"))
    if "!" in text:
        rep.error(label, "exclamation mark")
    if p0.AI_RE.search(text):
        rep.error(label, "mentions AI/automation")
    if "Lorenzo" not in (body_text or ""):
        rep.error(label, "not signed Lorenzo")
    for sentence in long_sentences(text, max_sentence_words):
        rep.warn(label, "sentence runs %d words (limit %d): %r"
                 % (len(sentence.split()), max_sentence_words, sentence[:90]))
    return rep
