"""The personalization line, the trigger variables, and the copy rules.

The line is the one thing in this pipeline a prospect actually reads, so it is
checked, not trusted: no em dashes, no exclamation marks, no mention of AI or
automation, no pitch, no price, and a length the first line of a cold email can
carry. A line that fails is rejected rather than shipped, because the campaign
substitutes ``{{personalization}}`` into the first sentence of every email and
a bad one is visible on 25 sends before anyone notices.

Trigger variables (Blueprint M5, "tag trigger signals so trigger campaigns are
trigger-based for your own prospects too"):

    cleaning_trigger    needs buildingType and metro
    recruiting_outbound needs specialty

A lead the factory cannot fill them for is staged with
``b_variant_eligible = false`` and a reason, never with a guess: 2,507 live
leads currently carry the filler specialty "your clients'" (measured read-only
2026-09-21), which is exactly what guessing produces.
"""
import logging
import os
import sys
from typing import Any, Callable, Dict, List, Optional

from shared import llm
from shared.paths import BASE_DIR

from services.list_factory import models
from services.list_factory import sources as sources_mod

logger = logging.getLogger("list_factory.personalize")

MAX_CHARS = 240
MIN_CHARS = 30

# Per-lead token averages measured on the fixture rehearsal, used to price the
# call the paid gate is about to refuse and the pipeline's projections. These
# are TEXT tokens. Thinking cannot be turned off on claude-opus-5-5 and bills
# as output, so every price built from them adds
# shared.llm.output_tokens_with_thinking()'s worst-case allowance for the one
# call a line takes. See usd_per_lead().
TOKENS_IN_PER_LEAD = 700
TOKENS_OUT_PER_LEAD = 70


def usd_per_lead(model: Optional[str] = None) -> float:
    """Projected cost of one personalization line: the measured text tokens
    plus worst-case thinking for its one call."""
    return llm.estimate_cost(model or llm.model_for("research"), TOKENS_IN_PER_LEAD,
                             llm.output_tokens_with_thinking(TOKENS_OUT_PER_LEAD, calls=1))

# Copy rules from CLAUDE.md and config/offers.md, in the order they are checked.
BANNED_SUBSTRINGS = (
    "—", "–",                      # em and en dash
    "!",                           # no exclamation marks
)
# Matched on WHOLE WORDS, never as substrings. The old test was
# ``word in " %s " % line.lower()`` with "ai " and " ai" in the list, so
# "Dubai Marina", "air ducts", "airport terminals" and "aisles" all read as AI
# talk and the good, checkable line was silently swapped for the dull
# template. "bot" matched "Bottom Line Bookkeeping", "llm" matched "Allman" and
# "Pllc": 88 of 13,988 real company names (0.63%) failed BOTH the model line
# and the template, and the fully paid lead was dropped at the last stage.
BANNED_WORDS = (
    "ai", "a.i.", "artificial intelligence", "automation", "automated", "bot", "bots",
    "chatgpt", "claude", "gpt", "llm", "our software", "our platform", "our tool",
    "as an ai", "language model",
)
# A personalization line is an observation, not an offer. These belong in the
# campaign body, which is written once and reviewed; a model writing them per
# lead is how an unreviewed price reaches a prospect.
BANNED_PITCH = (
    "guarantee", "$", "per month", "/mo", "retainer", "commission",
    "book a call", "15 minutes", "15-minute", "calendar", "hop on",
    "we help", "i help", "our clients", "case study",
)

SYSTEM = (
    "You write the first line of a cold email from Lorenzo, who runs a small outbound agency. "
    "One or two sentences, peer to peer, about the business in front of you. "
    "Rules: start with 'Hey <first name>,'. Say something specific and checkable from the "
    "information given. No pitch, no offer, no price, no call to action, no question about "
    "their goals. Never mention software, tools, AI or automation. No em dashes. No "
    "exclamation marks. Plain words, the way one owner writes to another."
)


class CopyRejected(Exception):
    pass


def _banned_hit(low: str, word: str) -> bool:
    """Whole-phrase for word-shaped rules, substring for symbol-shaped ones.

    ``keyword_hit`` anchors on word boundaries, which is right for "ai" and
    "bot" and wrong for "$" and "/mo": ``(?<![a-z0-9])\\$(?![a-z0-9])`` would
    never fire on "$500". So a phrase that starts and ends on an alphanumeric
    goes through the boundary matcher and everything else stays a substring.
    """
    from services.list_factory.icp import keyword_hit

    if word and word[0].isalnum() and word[-1].isalnum():
        return keyword_hit(low, word)
    return word in low


def check_copy(text: str, first_name: str = "") -> Optional[str]:
    """The reason this line cannot ship, or None."""
    line = models.clean_text(text)
    if not line:
        return "empty"
    if len(line) < MIN_CHARS:
        return "too short (%d chars)" % len(line)
    if len(line) > MAX_CHARS:
        return "too long (%d chars)" % len(line)
    for bad in BANNED_SUBSTRINGS:
        if bad in line:
            return "contains %r" % bad
    low = line.lower()
    for word in BANNED_WORDS:
        if _banned_hit(low, word):
            return "mentions %r" % word.strip()
    for word in BANNED_PITCH:
        if _banned_hit(low, word):
            return "pitches (%r belongs in the campaign body, not the personalization)" % word.strip()
    if "{{" in line or "}}" in line:
        return "contains an unrendered variable"
    if first_name and not line.lower().startswith("hey %s" % first_name.lower()):
        return "does not open with 'Hey %s,'" % first_name
    return None


def _facts(lead: Dict[str, Any]) -> str:
    bits = []
    for key, label in (
        ("company_name", "company"), ("city", "city"), ("state", "state"),
        ("industry", "industry"), ("keywords", "services"), ("description", "about"),
        ("headline", "headline"), ("company_size", "headcount"), ("research", "research"),
    ):
        value = models.clean_text(lead.get(key))
        if value:
            bits.append("%s: %s" % (label, value[:500]))
    return "\n".join(bits)


def build_prompt(lead: Dict[str, Any]) -> str:
    return (
        "First name: %s\n%s\n\nWrite the line. Return the line only, nothing else."
        % (lead.get("first_name") or "there", _facts(lead))
    )


def generate_line(lead: Dict[str, Any], model: Optional[str] = None, role: str = "personalize") -> str:
    install_offline_fakes()
    model = model or llm.model_for("research")
    if not llm.is_fake():
        # Same gate as Apify, Perplexity and MillionVerifier: a personalization
        # line bills real tokens and was previously outside every flag the
        # runbook names. Priced with worst-case thinking (usd_per_lead).
        from services.list_factory.sources import require_paid

        require_paid(
            "anthropic:%s" % model, 1,
            usd_per_lead(model),
            "one personalization line bills real tokens. Set LLM_FAKE=1 for a rehearsal.",
        )
    out = llm.complete(role, SYSTEM, build_prompt(lead), max_tokens=220, model=model)
    return models.clean_text(out if isinstance(out, str) else str(out))


# --------------------------------------------------------------- offline fake
# The library's generic fake answers "FAKE[personalize]: ...", which fails
# check_copy, so every lead in an LLM_FAKE run lands on the template fallback
# and the rehearsal never exercises the model path or the copy rules on a
# model-shaped line. This stand-in writes a line from the lead's own facts:
# deterministic, offline, free, and it goes through the same check_copy as a
# real one. Same shape as services.reply_engine.classify.install_offline_fakes.
def offline_line(system: str, user: str, json_mode: bool) -> str:
    fields = {}
    for line in (user or "").splitlines():
        key, _, value = line.partition(": ")
        if value:
            fields[key.strip().lower()] = value.strip()
    first = fields.get("first name") or "there"
    company = fields.get("company") or "your company"
    city = fields.get("city") or ""
    services = (fields.get("services") or "").split(",")[0].strip()
    where = " around %s" % city if city else ""
    what = services or "the accounts you look after"
    return "Hey %s, came across %s and saw you handle %s%s, figured I would reach out." % (
        first, company, what, where,
    )


def offline_fakes_wanted() -> bool:
    return llm.is_fake() and os.environ.get("LIST_FACTORY_OFFLINE_FAKES", "1") == "1"


def install_offline_fakes() -> None:
    if not offline_fakes_wanted():
        return
    if llm.fake_for("personalize") is None:
        llm.register_fake("personalize", offline_line)


if offline_fakes_wanted():
    install_offline_fakes()


def fallback_line(lead: Dict[str, Any]) -> str:
    """Template line for the case where the model's output fails the rules.

    Deliberately dull and always true: name, trade, city. It passes the same
    ``check_copy`` as everything else, so it can never be the thing that ships
    a banned word.
    """
    first = models.clean_text(lead.get("first_name")) or "there"
    what = models.clean_text(lead.get("niche_label")) or "what you do"
    city = models.clean_text(lead.get("city"))
    where = " out in %s" % city if city else ""
    return "Hey %s, came across %s and saw you handle %s%s, wanted to run something by you." % (
        first, models.clean_text(lead.get("company_name")) or "your company", what, where,
    )


def nameless_line(lead: Dict[str, Any]) -> str:
    """Last resort: the same dull line with the COMPANY NAME left out.

    Both the model line and ``fallback_line`` embed the company name, so a name
    that trips a copy rule failed both and the lead was rejected at the very
    last stage, after owner discovery and verification had already been paid
    for. "Bottom Line Bookkeeping", "Aire-master of America" and "Allman &
    Associates" are real examples. Dropping the name is a worse line; dropping
    the lead is a wasted $0.0165.
    """
    first = models.clean_text(lead.get("first_name")) or "there"
    what = models.clean_text(lead.get("niche_label")) or "what you do"
    city = models.clean_text(lead.get("city"))
    where = " out in %s" % city if city else ""
    return "Hey %s, came across your site and saw you handle %s%s, wanted to run something by you." % (
        first, what, where,
    )


def personalize(
    leads: List[Dict[str, Any]],
    niche_label: str = "",
    model: Optional[str] = None,
    generator: Optional[Callable[[Dict[str, Any]], str]] = None,
    on_lead: Optional[Callable[[int], None]] = None,
) -> Dict[str, Any]:
    """Write and check one line per lead. Rejects the ones that cannot ship."""
    summary = {"written": 0, "fallback": 0, "nameless": 0, "rejected": 0, "reasons": {}, "rejected_leads": []}
    generate = generator or (lambda lead: generate_line(lead, model=model))
    for lead in leads:
        lead["niche_label"] = niche_label
        first = models.clean_text(lead.get("first_name"))
        try:
            line = generate(lead)
        except sources_mod.PaidCallBlocked:
            raise
        except Exception as exc:  # noqa: BLE001 - a model failure is not a lost lead
            logger.warning("personalization failed for %s: %s", lead.get("lead_key"), exc)
            line = ""
        problem = check_copy(line, first) if line else "model returned nothing"
        source = "model"
        if problem:
            line = fallback_line(lead)
            problem = check_copy(line, first)
            source = "fallback"
        if problem:
            # The template failed too, which almost always means the company
            # name itself trips a rule. Try the line without it before
            # throwing away a lead that has already been paid for.
            line = nameless_line(lead)
            problem = check_copy(line, first)
            source = "nameless"
        if problem:
            models.reject(lead, models.REJECT_COPY, problem)
            summary["rejected"] += 1
            summary["reasons"][problem] = summary["reasons"].get(problem, 0) + 1
            # With the reason alone nobody can tell WHICH lead was binned.
            if len(summary["rejected_leads"]) < 25:
                summary["rejected_leads"].append({
                    "lead_key": lead.get("lead_key"), "company_name": lead.get("company_name"),
                    "reason": problem,
                })
            logger.warning("copy rules dropped a paid-for lead %s (%s): %s",
                           lead.get("lead_key"), lead.get("company_name"), problem)
            continue
        lead["personalization"] = line
        lead["personalization_model"] = (model or llm.model_for("research")) if source == "model" else "template"
        if source == "fallback":
            summary["fallback"] += 1
        elif source == "nameless":
            summary["nameless"] += 1
        summary["written"] += 1
        models.advance(lead, models.PERSONALIZED, source)
        if on_lead is not None:
            on_lead(1)
    return summary


# ------------------------------------------------------------ trigger tags
def _metro_index() -> Dict[str, str]:
    """city (lowercased) -> metro name, from execution/us_metros.py.

    Both the metro list and its subdivisions are indexed, so "Naperville" maps
    to "Chicago" rather than to nothing.
    """
    path = os.path.join(str(BASE_DIR), "execution")
    if path not in sys.path:
        sys.path.insert(0, path)
    try:
        import us_metros  # type: ignore
    except ImportError as exc:  # pragma: no cover - only when the file moves
        logger.warning("us_metros unavailable (%s); metro tagging falls back to the city name", exc)
        return {}
    index = {}
    for city, _state in getattr(us_metros, "US_METROS", []):
        index[city.lower()] = city
    for metro, suburbs in (getattr(us_metros, "METRO_SUBDIVISIONS", {}) or {}).items():
        index.setdefault(metro.lower(), metro)
        for suburb in suburbs:
            index.setdefault(suburb.lower(), metro)
    return index


_METRO_CACHE = {}  # type: Dict[str, Dict[str, str]]


def metro_for(city: str, state: str = "") -> str:
    """City -> the metro name to put in copy, or '' when we do not know one.

    Precedence: a city that is itself in ``US_METROS`` answers with its own
    name, and only a city that exists solely as somebody's suburb is rolled up
    to the parent metro. So Naperville stays Naperville and Oak Park becomes
    Chicago, which is how an owner in either place would describe their own
    service area.

    ``''`` is a real answer and is left alone. ``us_metros`` covers roughly 950
    US cities; a lead outside it gets no metro and is marked A-variant only
    rather than being told we watch triggers in a city we did not recognise.
    """
    if "index" not in _METRO_CACHE:
        _METRO_CACHE["index"] = _metro_index()
    index = _METRO_CACHE["index"]
    key = models.clean_text(city).lower()
    if not key:
        return ""
    return index.get(key, "")


def _match_map(text: str, mapping: Dict[str, List[str]]) -> str:
    """The mapping key with the most evidence in ``text``. A TIE answers ''.

    Two rules, both learned the hard way:

    1. Evidence is weighted by phrase length, so "medical office" (2 words)
       outweighs a passing "office" (1). A cleaner whose page says
       "restaurants, retail and the occasional medical suite" must not be
       tagged ``medical``.
    2. A tie answers '' rather than "whichever key the JSON lists first". Nine
       of the eighteen tagged leads in the recorded rehearsal were decided by a
       tie and five of those landed on ``medical`` off a 1-1 tie, purely
       because ``medical`` is the first key in cleaning.json. That word goes
       into the email. '' is the same answer an absent signal gets: staged for
       the A variant only, never guessed.
    """
    from services.list_factory.icp import keyword_hit, phrase_weight

    scores = {}  # type: Dict[str, int]
    for label, words in (mapping or {}).items():
        score = sum(phrase_weight(word) for word in (words or []) if keyword_hit(text, word))
        if score > 0:
            scores[label] = score
    if not scores:
        return ""
    best = max(scores.values())
    winners = [label for label, score in scores.items() if score == best]
    if len(winners) != 1:
        return ""
    return winners[0]


def tag_triggers(leads: List[Dict[str, Any]], rubric: Dict[str, Any]) -> Dict[str, Any]:
    """Fill the campaign's trigger variables, or mark the lead A-variant only."""
    required = list(rubric.get("trigger_variables") or [])
    summary = {"required": required, "eligible": 0, "not_eligible": 0, "missing": {}}
    building_map = rubric.get("building_types") or {}
    specialty_map = rubric.get("specialties") or {}
    allow_building_default = bool(rubric.get("building_type_default_allowed"))
    allow_specialty_default = bool(rubric.get("specialty_default_allowed"))

    for lead in leads:
        text = models.searchable_text(lead)
        if building_map:
            building = _match_map(text, building_map)
            if not building and allow_building_default:
                building = rubric.get("building_type_default") or ""
            lead["building_type"] = building
        if specialty_map:
            specialty = _match_map(text, specialty_map)
            if not specialty and allow_specialty_default:
                specialty = rubric.get("specialty_default") or ""
            lead["specialty"] = specialty
        lead["metro"] = metro_for(lead.get("city") or "", lead.get("state") or "")

        missing = []
        for variable in required:
            if variable == "buildingType" and not lead.get("building_type"):
                missing.append(variable)
            elif variable == "metro" and not lead.get("metro"):
                missing.append(variable)
            elif variable == "specialty" and not lead.get("specialty"):
                missing.append(variable)
        if missing:
            lead["b_variant_eligible"] = False
            lead["b_variant_reason"] = "missing %s" % ", ".join(missing)
            summary["not_eligible"] += 1
            for variable in missing:
                summary["missing"][variable] = summary["missing"].get(variable, 0) + 1
        else:
            lead["b_variant_eligible"] = True
            lead["b_variant_reason"] = ""
            summary["eligible"] += 1
    return summary
