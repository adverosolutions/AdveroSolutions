"""Phase 0 change-set library: validation, HTML <-> text, diffs, settings delta.

Pure functions only. Nothing here talks to the network; the apply script
(apply_instantly_phase0.py) wires these to shared.instantly.

Python 3.9 compatible.
"""
import difflib
import html as _html
import json
import os
import re
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
SEQUENCES_DIR = os.path.join(HERE, "sequences")
SETTINGS_PATH = os.path.join(HERE, "campaign_settings.json")
LABELS_PATH = os.path.join(HERE, "lead_labels.json")
SUBSEQUENCE_PATH = os.path.join(HERE, "subsequence_interested_quiet.json")

EM_DASH = "—"
EN_DASH = "–"
DASHES = (EM_DASH, EN_DASH)

MIN_SPINS = 3
MAX_SPINS = 5

# Copy defects M3.1 that must never reappear.
KNOWN_TYPOS = (
    "personaliztion",
    "outreach outreach",
    "ill shoot",
    "suprised",
    "candidate accounts",
)

# The other offer type's numbers must never leak into a campaign.
OFFER_MARKERS = {
    "reactivation": {"must": ["$150M", "$6M", "6 months"], "forbid": ["$180", "90 days in new"]},
    "outbound": {"must": ["$150M", "$180", "90 days"], "forbid": ["$6M", "6 months"]},
}

# Proof allowed outside the canonical roofer line (offers.md "Other allowed proof").
ALT_PROOF_MARKERS = ("$5M pipeline", "$1.5k", "35%", "$10k/mo")

VAR_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# Hard copy rules (Lorenzo): never mention AI or automation, no exclamation marks.
AI_RE = re.compile(r"\bAI\b|\bA\.I\.|automat", re.I)

# Money and time windows are contractual promises: every one in a body must be
# traceable to config/offers.md (the campaign's own row, its proof line, or the
# "Other allowed proof" sentence). A reactivation offer has no guarantee at all.
MONEY_RE = re.compile(r"\$\s?(\d[\d,]*(?:\.\d+)?)\s*([MmKk])?")
BARE_AMOUNT_RE = re.compile(r"\b(\d[\d,]*(?:\.\d+)?)\b")
PERIOD_RE = re.compile(r"\b(\d+)[\s-]+(day|days|week|weeks|month|months|year|years)\b", re.I)
GUARANTEE_RE = re.compile(r"\bguarantee|\bmoney back\b|\bgift card\b", re.I)

# Step keys every live step carries; a PATCH that drops them silently re-defaults
# the cadence on all six campaigns (see runbooks/phase0.md known gaps).
LIVE_STEP_KEYS = ("delay_unit", "pre_delay_unit")


# --------------------------------------------------------------------------
# files
def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def load_settings(path: str = SETTINGS_PATH) -> Dict[str, Any]:
    return load_json(path)


def load_sequence(campaign_key: str, sequences_dir: str = SEQUENCES_DIR) -> Dict[str, Any]:
    return load_json(os.path.join(sequences_dir, "%s.json" % campaign_key))


# --------------------------------------------------------------------------
# html <-> text
_BR_RE = re.compile(r"<br\s*/?>", re.I)
_DIV_CLOSE_RE = re.compile(r"</div>", re.I)
_TAG_RE = re.compile(r"<[^>]+>")


def html_to_text(body_html: str) -> str:
    """Instantly stores bodies as <div>line</div><div><br /></div>. Flatten
    to plain text with blank lines preserved."""
    if not body_html:
        return ""
    s = _BR_RE.sub("\n", body_html)
    s = _DIV_CLOSE_RE.sub("\n", s)
    s = _TAG_RE.sub("", s)
    s = _html.unescape(s)
    s = s.replace("\r", "")
    s = re.sub(r"[ \t]+\n", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip("\n")


def text_to_html(text: str) -> str:
    """Inverse of html_to_text using the exact shape the live snapshot uses."""
    out = []
    for line in text.strip("\n").split("\n"):
        if line.strip() == "":
            out.append("<div><br /></div>")
        else:
            out.append("<div>%s</div>" % _html.escape(line, quote=False))
    return "".join(out)


# --------------------------------------------------------------------------
# tag parsing ({{var}} and {{RANDOM | a | b}})
class TagError(ValueError):
    pass


def find_tags(text: str) -> List[Tuple[int, int, str]]:
    """Return top-level (start, end, inner) for every {{...}} tag, honouring
    nesting. Raises TagError when braces are unbalanced."""
    tags = []
    i = 0
    n = len(text)
    while i < n:
        if text.startswith("{{", i):
            depth = 1
            j = i + 2
            while j < n and depth > 0:
                if text.startswith("{{", j):
                    depth += 1
                    j += 2
                elif text.startswith("}}", j):
                    depth -= 1
                    j += 2
                else:
                    j += 1
            if depth != 0:
                raise TagError("unbalanced '{{' at offset %d: %r" % (i, text[i:i + 40]))
            tags.append((i, j, text[i + 2:j - 2]))
            i = j
        elif text.startswith("}}", i):
            raise TagError("stray '}}' at offset %d: %r" % (i, text[max(0, i - 30):i + 2]))
        else:
            i += 1
    return tags


def _split_top_level(inner: str, sep: str = "|") -> List[str]:
    parts = []  # type: List[str]
    depth = 0
    cur = []  # type: List[str]
    i = 0
    n = len(inner)
    while i < n:
        if inner.startswith("{{", i):
            depth += 1
            cur.append("{{")
            i += 2
            continue
        if inner.startswith("}}", i):
            depth -= 1
            cur.append("}}")
            i += 2
            continue
        ch = inner[i]
        if ch == sep and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
        i += 1
    parts.append("".join(cur))
    return parts


def iter_spins(text: str) -> Iterator[Tuple[str, List[str]]]:
    """Yield (raw_tag, options) for every RANDOM spin, including nested ones."""
    for _s, _e, inner in find_tags(text):
        head = inner.strip().split("|", 1)[0].strip()
        if head.upper() == "RANDOM":
            parts = _split_top_level(inner)
            options = [p.strip() for p in parts[1:]]
            yield "{{%s}}" % inner, options
            for opt in options:
                for sub in iter_spins(opt):
                    yield sub


def merge_variables(text: str) -> Set[str]:
    """Every non-RANDOM {{name}} in the text, including inside spin options."""
    names = set()  # type: Set[str]
    for _s, _e, inner in find_tags(text):
        head = inner.strip().split("|", 1)[0].strip()
        if head.upper() == "RANDOM":
            for opt in _split_top_level(inner)[1:]:
                names |= merge_variables(opt)
        else:
            names.add(inner.strip())
    return names


def campaign_variables(campaign: Dict[str, Any]) -> Set[str]:
    """Variable names a live campaign knows (core + custom, flagged true)."""
    names = set()  # type: Set[str]
    for group in ("core_variables", "custom_variables"):
        for k, v in (campaign.get(group) or {}).items():
            if v:
                names.add(k)
    return names


# --------------------------------------------------------------------------
# validation
class Report(object):
    def __init__(self, campaign_key: str):
        self.campaign_key = campaign_key
        self.errors = []  # type: List[str]
        self.warnings = []  # type: List[str]

    def error(self, where: str, msg: str) -> None:
        self.errors.append("%s: %s" % (where, msg))

    def warn(self, where: str, msg: str) -> None:
        self.warnings.append("%s: %s" % (where, msg))

    @property
    def ok(self) -> bool:
        return not self.errors

    def summary(self) -> str:
        lines = ["[%s] %s" % (self.campaign_key, "OK" if self.ok else "%d error(s)" % len(self.errors))]
        for e in self.errors:
            lines.append("  ERROR %s" % e)
        for w in self.warnings:
            lines.append("  warn  %s" % w)
        return "\n".join(lines)


def iter_variants(sequence_doc: Dict[str, Any]) -> Iterator[Tuple[int, int, Dict[str, Any], Dict[str, Any]]]:
    """Yield (step_index, variant_index, step, variant) for a sequences doc."""
    for seq in sequence_doc.get("sequences", []):
        for si, step in enumerate(seq.get("steps", [])):
            for vi, var in enumerate(step.get("variants", [])):
                yield si, vi, step, var


def proof_lines_from_offers(offers_md: str) -> Dict[str, str]:
    """Pull the two verbatim proof lines out of config/offers.md's table."""
    out = {}  # type: Dict[str, str]
    for line in offers_md.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 2 and cells[0] in ("Reactivation", "Outbound / trigger"):
            proof = cells[1].strip().strip('"')
            out["reactivation" if cells[0] == "Reactivation" else "outbound"] = proof
    return out


def offer_rows_from_offers(offers_md: str) -> Dict[str, str]:
    """{campaign_key: the whole 'six offers' row as text} from config/offers.md."""
    out = {}  # type: Dict[str, str]
    for line in offers_md.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 3 and re.match(r"^[a-z][a-z_]+$", cells[0]):
            out[cells[0]] = " ".join(cells)
    return out


def alt_proof_sentence(offers_md: str) -> str:
    for line in offers_md.splitlines():
        if line.startswith("Other allowed proof"):
            return line
    return ""


def money_values(text: str) -> Set[float]:
    """Every dollar figure as a number: $24K, $24,000 and $24000 all give 24000."""
    vals = set()  # type: Set[float]
    for m in MONEY_RE.finditer(text):
        num = float(m.group(1).replace(",", ""))
        suf = (m.group(2) or "").lower()
        if suf == "m":
            num *= 1000000
        elif suf == "k":
            num *= 1000
        vals.add(round(num, 2))
    return vals


def period_phrases(text: str) -> Set[str]:
    """{'90 day', '6 month'} for every "<n> days/months/..." window."""
    out = set()  # type: Set[str]
    for m in PERIOD_RE.finditer(text):
        out.add("%s %s" % (m.group(1), m.group(2).lower().rstrip("s")))
    return out


def allowed_offer_numbers(campaign_key: str, offer: str, offers_md: str) -> Tuple[Set[float], Set[str]]:
    """The money figures and time windows this campaign is allowed to promise:
    its own offers.md row, its offer type's proof line, and the 'Other allowed
    proof' sentence. Nothing else may appear in customer-facing copy."""
    corpus = " ".join([
        offer_rows_from_offers(offers_md).get(campaign_key, ""),
        proof_lines_from_offers(offers_md).get(offer, ""),
        alt_proof_sentence(offers_md),
    ])
    money = money_values(corpus)
    # Ranges in offers.md are written "$2,500-5,000/mo": the second number has
    # no dollar sign, so pick up bare four-figure-plus amounts from the row too.
    for m in BARE_AMOUNT_RE.finditer(corpus):
        raw = m.group(1)
        num = float(raw.replace(",", ""))
        if "," in raw or num >= 1000:
            money.add(round(num, 2))
    return money, period_phrases(corpus)


def validate_sequence(
    campaign_key: str,
    sequence_doc: Dict[str, Any],
    live_campaign: Dict[str, Any],
    settings: Dict[str, Any],
    offers_md: str,
) -> Report:
    rep = Report(campaign_key)
    cfg = (settings.get("campaigns") or {}).get(campaign_key)
    if cfg is None:
        rep.error("settings", "campaign key %r missing from campaign_settings.json" % campaign_key)
        return rep
    offer = cfg.get("offer")
    if offer not in OFFER_MARKERS:
        rep.error("settings", "offer must be reactivation|outbound, got %r" % offer)
        return rep

    proof_lines = proof_lines_from_offers(offers_md)
    canonical = proof_lines.get(offer)
    if not canonical:
        rep.error("offers.md", "could not find the %s proof line in offers.md" % offer)
    cfg_proof = (settings.get("proof") or {}).get(offer)
    if canonical and cfg_proof and cfg_proof != canonical:
        rep.error("settings.proof", "campaign_settings.json proof for %s differs from offers.md" % offer)

    known_vars = campaign_variables(live_campaign)
    new_vars = set(cfg.get("new_variables") or [])
    allowed_money, allowed_periods = allowed_offer_numbers(campaign_key, offer, offers_md)

    seqs = sequence_doc.get("sequences")
    if not isinstance(seqs, list) or len(seqs) != 1:
        rep.error("shape", "expected exactly one sequences entry")
        return rep
    steps = seqs[0].get("steps") or []
    if len(steps) < 3:
        rep.error("shape", "expected 3 steps, got %d" % len(steps))

    for si, vi, step, var in iter_variants(sequence_doc):
        where = "step%d/variant%s" % (si + 1, "AB"[vi] if vi < 2 else str(vi))
        if step.get("type") != "email":
            rep.error(where, "step type must be 'email'")
        if not isinstance(step.get("delay"), int) or step["delay"] < 0:
            rep.error(where, "delay must be a non-negative int")
        subject = var.get("subject")
        body = var.get("body")
        if not isinstance(subject, str) or not isinstance(body, str) or not body.strip():
            rep.error(where, "subject must be a string and body a non-empty string")
            continue
        text = html_to_text(body)
        combined = subject + "\n" + text

        # em / en dashes
        for d in DASHES:
            if d in combined:
                rep.error(where, "contains %s dash" % ("em" if d == EM_DASH else "en"))

        # typos
        low = combined.lower()
        for t in KNOWN_TYPOS:
            if t in low:
                rep.error(where, "known typo/defect present: %r" % t)

        # spintax
        try:
            spins = list(iter_spins(combined))
        except TagError as exc:
            rep.error(where, "spintax/tag error: %s" % exc)
            continue
        for raw, options in spins:
            if len(options) < 2:
                rep.error(where, "spin needs >=2 options: %s" % raw[:60])
            if any(o == "" for o in options):
                rep.error(where, "spin has an empty option: %s" % raw[:60])
            if len(set(options)) != len(options):
                rep.error(where, "spin repeats an option, so it renders one string for every lead: %s" % raw[:60])
            for o in options:
                if VAR_NAME_RE.match(o) and o in known_vars | new_vars:
                    rep.error(where, "merge variable used as a spin option: %s" % raw[:60])
        n_spins = len(spins)
        if n_spins < MIN_SPINS or n_spins > MAX_SPINS:
            rep.error(where, "%d spin points; need %d-%d" % (n_spins, MIN_SPINS, MAX_SPINS))

        # merge variables
        for name in sorted(merge_variables(combined)):
            if not VAR_NAME_RE.match(name):
                rep.error(where, "malformed tag {{%s}}" % name)
            elif name in known_vars:
                pass
            elif name in new_vars:
                rep.warn(where, "{{%s}} is NEW for this campaign; leads must carry it before apply" % name)
            else:
                rep.error(where, "{{%s}} not in campaign variables %s" % (name, sorted(known_vars)))

        # {{personalization}} first line on step 1
        first_line = text.split("\n", 1)[0].strip()
        if si == 0 and first_line != "{{personalization}}":
            rep.error(where, "step 1 must start with {{personalization}} on its own line")

        # thread rules: step 2 continues the thread, step 3 is a new thread
        if si == 0 and not subject.strip():
            rep.error(where, "step 1 needs a subject")
        if si == 1 and subject.strip():
            rep.error(where, "step 2 must keep an empty subject (same thread)")
        if si == 2 and not subject.strip():
            rep.error(where, "step 3 must carry a fresh subject (new thread)")

        # proof points
        markers = OFFER_MARKERS[offer]
        for bad in markers["forbid"]:
            if bad in text:
                rep.error(where, "other offer's proof number present: %r" % bad)
        if si in (0, 1):
            missing = [m for m in markers["must"] if m not in text]
            if missing:
                rep.error(where, "canonical proof numbers missing: %s" % missing)
            if si == 0 and vi == 0 and canonical and canonical not in text:
                rep.error(where, "variant A must carry the offers.md proof line verbatim")
        else:
            has_alt = any(m in text for m in ALT_PROOF_MARKERS)
            has_canon = all(m in text for m in markers["must"])
            if not (has_alt or has_canon):
                rep.error(where, "step 3 needs a different (allowed) proof point or the canonical one")

        # voice (hard rules: these are errors, never warnings)
        if AI_RE.search(combined):
            rep.error(where, "mentions AI/automation")
        if "!" in combined:
            rep.error(where, "exclamation mark")
        if "Lorenzo" not in text:
            rep.error(where, "not signed Lorenzo")

        # every promise must come from offers.md
        for amount in sorted(money_values(combined) - allowed_money):
            rep.error(where, "dollar figure %s is not in this campaign's offers.md row or proof line" % _fmt_money(amount))
        for window in sorted(period_phrases(combined) - allowed_periods):
            rep.error(where, "time window %ss is not in this campaign's offers.md row or proof line" % window)
        if offer == "reactivation":
            g = GUARANTEE_RE.search(combined)
            if g:
                rep.error(where, "guarantee language %r on a reactivation offer, which has no guarantee in offers.md" % g.group(0))

    # A/B variants that are byte-identical make the 500-send verdict meaningless
    for si, step in enumerate(steps):
        seen = {}  # type: Dict[Tuple[str, str], str]
        for vi, var in enumerate(step.get("variants") or []):
            sig = (var.get("subject") or "", var.get("body") or "")
            label = "step%d/variant%s" % (si + 1, "AB"[vi] if vi < 2 else str(vi))
            if sig in seen:
                rep.error(label, "identical to %s; the A/B test would compare a variant against itself" % seen[sig])
            seen[sig] = label

    # delays: step1 -> step2 -> step3 should land day 3 and day 7
    if len(steps) >= 3:
        d1 = steps[0].get("delay")
        d2 = steps[1].get("delay")
        if isinstance(d1, int) and isinstance(d2, int) and d1 + d2 != 7:
            rep.warn("delays", "step 3 lands on day %s, brief asks for day 7" % (d1 + d2))
    if len(steps) >= 1 and len(steps[0].get("variants", [])) != 2:
        rep.error("step1", "needs exactly variants A and B")
    return rep


def validate_subsequence_copy(
    campaign_key: str,
    subsequence: Dict[str, Any],
    settings: Dict[str, Any],
    offers_md: str,
    known_vars: Optional[Set[str]] = None,
) -> Report:
    """The same money / period / guarantee / voice gate the campaign sequences
    get, applied to the Interested-quiet subsequence bodies.

    The subsequence is the only lead-facing copy in Phase 0 that used to reach
    POST /subsequences without any offers.md check, and it goes to leads
    Instantly has already marked interested. `known_vars` is optional because
    the applier has no campaign snapshot in hand; when it is None the merge
    variables are only checked for shape, not for membership.
    """
    rep = Report(campaign_key)
    cfg = (settings.get("campaigns") or {}).get(campaign_key)
    if cfg is None:
        rep.error("settings", "campaign key %r missing from campaign_settings.json" % campaign_key)
        return rep
    offer = cfg.get("offer")
    if offer not in OFFER_MARKERS:
        rep.error("settings", "offer must be reactivation|outbound, got %r" % offer)
        return rep
    new_vars = set(cfg.get("new_variables") or [])
    allowed_money, allowed_periods = allowed_offer_numbers(campaign_key, offer, offers_md)

    steps = (subsequence.get("sequences") or [{}])[0].get("steps") or []
    if not steps:
        rep.error("shape", "subsequence has no steps")
    for si, step in enumerate(steps):
        for vi, var in enumerate(step.get("variants") or []):
            where = "d%d/variant%s" % ([1, 3, 7][si] if si < 3 else si + 1, "AB"[vi] if vi < 2 else str(vi))
            subject = var.get("subject")
            body = var.get("body")
            if not isinstance(subject, str) or not isinstance(body, str) or not body.strip():
                rep.error(where, "subject must be a string and body a non-empty string")
                continue
            text = html_to_text(body)
            combined = subject + "\n" + text

            for d in DASHES:
                if d in combined:
                    rep.error(where, "contains %s dash" % ("em" if d == EM_DASH else "en"))
            low = combined.lower()
            for t in KNOWN_TYPOS:
                if t in low:
                    rep.error(where, "known typo/defect present: %r" % t)
            try:
                spins = list(iter_spins(combined))
            except TagError as exc:
                rep.error(where, "spintax/tag error: %s" % exc)
                continue
            for raw, options in spins:
                if len(options) < 2:
                    rep.error(where, "spin needs >=2 options: %s" % raw[:60])
                if any(o == "" for o in options):
                    rep.error(where, "spin has an empty option: %s" % raw[:60])
                if len(set(options)) != len(options):
                    rep.error(where, "spin repeats an option: %s" % raw[:60])
            for name in sorted(merge_variables(combined)):
                if not VAR_NAME_RE.match(name):
                    rep.error(where, "malformed tag {{%s}}" % name)
                elif known_vars is not None and name not in known_vars and name not in new_vars:
                    rep.error(where, "{{%s}} not in campaign variables %s" % (name, sorted(known_vars)))
            if AI_RE.search(combined):
                rep.error(where, "mentions AI/automation")
            if "!" in combined:
                rep.error(where, "exclamation mark")
            if "Lorenzo" not in text:
                rep.error(where, "not signed Lorenzo")
            if subject.strip():
                rep.error(where, "subsequence steps keep an empty subject (same thread)")
            for amount in sorted(money_values(combined) - allowed_money):
                rep.error(where, "dollar figure %s is not in this campaign's offers.md row or proof line"
                          % _fmt_money(amount))
            for window in sorted(period_phrases(combined) - allowed_periods):
                rep.error(where, "time window %ss is not in this campaign's offers.md row or proof line" % window)
            if offer == "reactivation":
                g = GUARANTEE_RE.search(combined)
                if g:
                    rep.error(where, "guarantee language %r on a reactivation offer, which has no guarantee "
                                     "in offers.md" % g.group(0))
    return rep


def validate_labels(labels: List[Dict[str, Any]], expected: List[str]) -> List[str]:
    errors = []
    seen = set()
    for lab in labels:
        name = lab.get("label")
        if name in seen:
            errors.append("duplicate label %r" % name)
        seen.add(name)
        if lab.get("interest_status_label") not in ("positive", "negative", "neutral"):
            errors.append("%s: interest_status_label must be positive|negative|neutral" % name)
        desc = lab.get("description") or ""
        if len(desc) < 40:
            errors.append("%s: description too short for the AI labeler" % name)
        if any(d in desc for d in DASHES):
            errors.append("%s: description contains a dash" % name)
        # R9 (owner decision 2026-09-22): AI labelling stays off until every
        # detector reads the custom values these labels are given. A custom
        # value arriving on replies today makes the 07:30 sweep, the campaign
        # verdicts and the retro counters miscount (GOL-11).
        if lab.get("use_with_ai") is not False:
            errors.append("%s: use_with_ai must be false until every detector reads the new "
                          "label values (R9)" % name)
        examples = lab.get("examples")
        if not isinstance(examples, list) or not examples:
            errors.append("%s: needs a non-empty examples list (the tests read it)" % name)
        else:
            for ex in examples:
                if ex not in desc:
                    errors.append("%s: example %r is not in the description the labeler reads" % (name, ex))
    missing = [e for e in expected if e not in seen]
    if missing:
        errors.append("missing labels: %s" % missing)
    return errors


# --------------------------------------------------------------------------
# diffs
def plain_text_variants(sequence_doc: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    """{"step1/A": {"subject":..., "text":...}, ...}"""
    out = {}  # type: Dict[str, Dict[str, str]]
    for si, vi, step, var in iter_variants(sequence_doc):
        key = "step%d/%s" % (si + 1, "AB"[vi] if vi < 2 else str(vi))
        out[key] = {
            "subject": var.get("subject") or "",
            "text": html_to_text(var.get("body") or ""),
            "delay": str(step.get("delay")),
        }
    return out


def sequence_diff(live_campaign: Dict[str, Any], new_doc: Dict[str, Any], campaign_key: str) -> str:
    """Unified diff of plain-text bodies (and subjects) old -> new, per variant."""
    old = plain_text_variants({"sequences": live_campaign.get("sequences", [])})
    new = plain_text_variants(new_doc)
    chunks = []
    for key in sorted(set(old) | set(new), key=_variant_sort_key):
        o = old.get(key)
        n = new.get(key)
        o_lines = _variant_lines(o) if o else []
        n_lines = _variant_lines(n) if n else []
        label = key
        if o is None:
            label += " (NEW)"
        elif n is None:
            label += " (REMOVED)"
        diff = list(
            difflib.unified_diff(
                o_lines, n_lines,
                fromfile="live/%s/%s" % (campaign_key, key),
                tofile="new/%s/%s" % (campaign_key, key),
                lineterm="",
            )
        )
        if diff:
            chunks.append("### %s\n%s" % (label, "\n".join(diff)))
        else:
            chunks.append("### %s\n(unchanged)" % label)
    return "\n\n".join(chunks)


def _variant_lines(v: Dict[str, str]) -> List[str]:
    return ["SUBJECT: %s" % v["subject"], "DELAY: %s" % v["delay"], ""] + v["text"].split("\n")


def _variant_sort_key(key: str) -> Tuple[int, str]:
    m = re.match(r"step(\d+)/(.*)", key)
    return (int(m.group(1)), m.group(2)) if m else (99, key)


def settings_delta(live_campaign: Dict[str, Any], desired: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """{key: {"live": x, "desired": y, "changed": bool}} for every desired key."""
    out = {}  # type: Dict[str, Dict[str, Any]]
    for k, want in desired.items():
        have = live_campaign.get(k)
        out[k] = {"live": have, "desired": want, "changed": have != want}
    return out


def _fmt_money(amount: float) -> str:
    return "$%s" % ("{:,.0f}".format(amount) if float(amount).is_integer() else "{:,.2f}".format(amount))


def dropped_step_keys(live_campaign: Dict[str, Any], new_doc: Dict[str, Any]) -> List[str]:
    """Keys the live steps carry that the staged steps do not. A PATCH replaces
    `sequences` wholesale, so anything missing here is silently deleted from the
    live object and re-defaulted by Instantly."""
    live_steps = (live_campaign.get("sequences") or [{}])[0].get("steps") or []
    new_steps = (new_doc.get("sequences") or [{}])[0].get("steps") or []
    lost = set()  # type: Set[str]
    for i, live_step in enumerate(live_steps):
        new_step = new_steps[i] if i < len(new_steps) else (new_steps[-1] if new_steps else {})
        for k in live_step:
            if k != "variants" and k not in new_step:
                lost.add(k)
    return sorted(lost)


def build_patch(sequence_doc: Dict[str, Any], desired_settings: Dict[str, Any]) -> Dict[str, Any]:
    """The exact PATCH /campaigns/{id} body for one campaign."""
    patch = {"sequences": sequence_doc["sequences"]}  # type: Dict[str, Any]
    patch.update(desired_settings)
    return patch


def desired_settings_for(cfg: Dict[str, Any], campaign_schedule: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """API-settable settings from a campaign_settings.json entry (ignores notes).

    `campaign_schedule` is the file-level default; a campaign may override it
    with its own key. It is in the PATCH allow-list (config/instantly_api_contract.md)
    and matters: five of six campaigns send 07:00-19:00 America/Detroit including
    Saturdays today, which is 06:00 CT and outside shared.settings.SEND_WINDOW.
    """
    out = {
        "pl_value": cfg["pl_value"],
        "stop_on_auto_reply": cfg["stop_on_auto_reply"],
        "open_tracking": cfg["open_tracking"],
        "link_tracking": cfg["link_tracking"],
    }  # type: Dict[str, Any]
    sched = cfg.get("campaign_schedule") or campaign_schedule
    if sched:
        out["campaign_schedule"] = sched
    return out


def desired_settings(cfg_all: Dict[str, Any], campaign_key: str) -> Dict[str, Any]:
    """desired_settings_for() with the file-level campaign_schedule resolved."""
    return desired_settings_for(cfg_all["campaigns"][campaign_key], cfg_all.get("campaign_schedule"))
