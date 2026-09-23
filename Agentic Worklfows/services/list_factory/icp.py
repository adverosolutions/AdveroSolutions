"""ICP scoring: does this business actually do the thing?

Three layers, cheapest first, because the September lists mailed a snow-removal
company as a commercial cleaner and that miss costs a domain's reputation, not
a fraction of a cent:

1. ``hard_reject_keywords`` from ``config/icp/<niche>.json``. Free, deterministic,
   and it is what actually catches "snow removal". A hard reject is final: the
   model never gets a chance to argue it back in.
2. ``hard_accept_keywords``. Free. A business whose own description says
   "commercial janitorial" does not need a model to confirm it.
3. Haiku, in batches, on whatever is left. Confidence below the rubric's
   ``escalate_below`` escalates that one lead to Sonnet (CLAUDE.md: "Haiku for
   classification, escalate < 0.8 confidence to Sonnet"), up to a per-run cap.
   Anything still unsure after that is REJECTED, not accepted: an unsure lead
   mailed is a hostile reply, an unsure lead dropped is a fraction of a cent.
"""
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

from shared import llm
from shared.paths import CONFIG_DIR

from services.list_factory import models
from services.list_factory.sources import require_paid

logger = logging.getLogger("list_factory.icp")

DEFAULT_BATCH_SIZE = 20
DEFAULT_MAX_ESCALATIONS = 50

# Per-business token averages measured on the fixture rehearsal, used only to
# price the call the paid gate is about to refuse.
TOKENS_IN_PER_BUSINESS = 140
TOKENS_OUT_PER_BUSINESS = 25

# Fields a hard-accept phrase is allowed to fire from. NOT ``keywords``: the
# Apify actor echoes its own search terms back into every row ("janitorial
# services, facilities services"), so 27 of the 58 recorded businesses carried
# "janitorial" for no reason other than the query we sent. A bin-cleaning
# company and two window washers were accepted at confidence 1.0 before the
# model ever saw them, which is exactly the 'snow-removal company mailed as a
# cleaner' failure this rubric exists to stop. Hard REJECT still reads
# everything: over-rejecting on an echoed term costs a fraction of a cent, and
# no query we send contains a reject phrase.
HARD_ACCEPT_FIELDS = ("company_name", "description", "headline")

VERDICT_ACCEPT = "accept"
VERDICT_REJECT = "reject"
VERDICT_UNSURE = "unsure"

SYSTEM = (
    "You screen businesses for a B2B outreach list. You are given a niche question and a "
    "numbered list of businesses with whatever public text we have about each one. For each "
    "business answer whether it genuinely matches the question. Judge only on the evidence "
    "given; do not assume a business does something because its name hints at it. "
    "Answer 'unsure' when the evidence does not settle it. Being wrong in the accepting "
    "direction is far more expensive than being wrong in the rejecting direction."
)


class RubricError(Exception):
    pass


def icp_dir() -> str:
    override = os.environ.get("LIST_FACTORY_ICP_DIR")
    return override or os.path.join(str(CONFIG_DIR), "icp")


def load_rubric(niche: str) -> Dict[str, Any]:
    path = os.path.join(icp_dir(), "%s.json" % models.slug(niche))
    try:
        with open(path, "r", encoding="utf-8") as fh:
            rubric = json.load(fh)
    except (OSError, IOError) as exc:
        raise RubricError("no ICP rubric for niche %r at %s (%s)" % (niche, path, exc))
    if not rubric.get("question"):
        raise RubricError("rubric %s has no question" % path)
    return rubric


def available_niches() -> List[str]:
    try:
        return sorted(
            name[:-5] for name in os.listdir(icp_dir())
            if name.endswith(".json") and not name.startswith("suppression")
        )
    except OSError:
        return []


# ------------------------------------------------------------ rule layer
_PATTERN_CACHE = {}  # type: Dict[str, Any]


def keyword_hit(text: str, word: str) -> bool:
    """Whole-phrase match, not a bare substring.

    A plain ``"house cleaning" in text`` rejected "Industrial and **wareHOUSE
    CLEANING** crews" as a residential maid service, and it would do the same
    to "greenhouse cleaning" or "Powerhouse Cleaning Co". The phrase has to
    start and end on a word boundary. Caught in the first fixture rehearsal,
    where it silently dropped a good industrial lead: a rule that quietly
    removes good leads is worse than one that lets a few through, because
    nothing downstream ever reports it.
    """
    word = (word or "").strip().lower()
    if not word:
        return False
    pattern = _PATTERN_CACHE.get(word)
    if pattern is None:
        pattern = re.compile(r"(?<![a-z0-9])%s(?![a-z0-9])" % re.escape(word))
        _PATTERN_CACHE[word] = pattern
    return bool(pattern.search(text))


_WORDS = re.compile(r"[a-z0-9]+")


def phrase_weight(word: str) -> int:
    """How much evidence one matching phrase is worth: its word count.

    "medical office cleaning" is a stronger signal than a bare "medical", and
    a category picked by a 1-1 tie is a category picked by the order of keys in
    a JSON file. Used by the trigger tagger, which writes its answer into
    prospect-facing copy.
    """
    return max(1, len(_WORDS.findall((word or "").lower())))


def accept_text(lead: Dict[str, Any]) -> str:
    """The lead's own words, with the scraper's echoed query left out."""
    parts = [lead.get(field) for field in HARD_ACCEPT_FIELDS]
    return " ".join(models.clean_text(p).lower() for p in parts if p)


def rule_verdict(lead: Dict[str, Any], rubric: Dict[str, Any]) -> Dict[str, Any]:
    """Free keyword pass. Returns {'verdict', 'reason'} or verdict 'unsure'."""
    text = models.searchable_text(lead)
    if not text:
        return {"verdict": VERDICT_UNSURE, "reason": "no text to judge"}
    for word in rubric.get("hard_reject_keywords") or []:
        if keyword_hit(text, word):
            return {"verdict": VERDICT_REJECT, "reason": "hard reject keyword: %s" % word}
    own_words = accept_text(lead)
    for word in rubric.get("hard_accept_keywords") or []:
        if own_words and keyword_hit(own_words, word):
            return {"verdict": VERDICT_ACCEPT, "reason": "hard accept keyword: %s" % word}
    return {"verdict": VERDICT_UNSURE, "reason": "no decisive keyword"}


# ------------------------------------------------------------- model layer
def _business_line(index: int, lead: Dict[str, Any]) -> str:
    bits = [
        "name: %s" % (lead.get("company_name") or "?"),
        "location: %s, %s" % (lead.get("city") or "?", lead.get("state") or "?"),
    ]
    for key, label in (("industry", "industry"), ("keywords", "keywords"),
                       ("description", "description"), ("headline", "headline"),
                       ("website", "website")):
        value = models.clean_text(lead.get(key))
        if value:
            bits.append("%s: %s" % (label, value[:400]))
    return "%d. %s" % (index, " | ".join(bits))


def build_prompt(batch: List[Dict[str, Any]], rubric: Dict[str, Any]) -> str:
    lines = [
        "QUESTION: %s" % rubric["question"],
        "",
        "Counts as a match: %s" % ", ".join(rubric.get("accept_signals") or []),
        "Does NOT count: %s" % ", ".join(rubric.get("reject_signals") or []),
        "",
        "BUSINESSES:",
    ]
    for i, lead in enumerate(batch, start=1):
        lines.append(_business_line(i, lead))
    lines += [
        "",
        'Return {"results": [{"n": <number>, "verdict": "accept"|"reject"|"unsure", '
        '"confidence": <0-1>, "reason": "<8 words or fewer>"}]} with one entry per business, '
        "in order, covering every number.",
    ]
    return "\n".join(lines)


def _parse_results(raw: Any, size: int) -> Optional[List[Dict[str, Any]]]:
    """Pull the per-business rows out of whatever came back.

    Returns None when the response is not usable, which the caller treats as
    'the model did not answer' and falls back to unsure -> reject. A partial
    answer is not stretched to cover the businesses it skipped.
    """
    if not isinstance(raw, dict):
        return None
    rows = raw.get("results")
    if not isinstance(rows, list) or not rows:
        return None
    by_n = {}  # type: Dict[int, Dict[str, Any]]
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            n = int(row.get("n"))
        except (TypeError, ValueError):
            continue
        if 1 <= n <= size:
            by_n[n] = row
    if not by_n:
        return None
    out = []
    for n in range(1, size + 1):
        row = by_n.get(n)
        if row is None:
            out.append({"verdict": VERDICT_UNSURE, "confidence": 0.0, "reason": "not answered"})
            continue
        verdict = str(row.get("verdict") or "").strip().lower()
        if verdict not in (VERDICT_ACCEPT, VERDICT_REJECT, VERDICT_UNSURE):
            verdict = VERDICT_UNSURE
        try:
            confidence = float(row.get("confidence"))
        except (TypeError, ValueError):
            confidence = 0.0
        out.append({
            "verdict": verdict,
            "confidence": max(0.0, min(1.0, confidence)),
            "reason": models.clean_text(row.get("reason"))[:120],
        })
    return out


def score_batch(batch: List[Dict[str, Any]], rubric: Dict[str, Any], model: Optional[str] = None,
                role: str = "icp_score") -> List[Dict[str, Any]]:
    """One model call for the whole batch."""
    if not batch:
        return []
    install_offline_fakes()
    model = model or llm.model_for("classify")
    if not llm.is_fake():
        # Anthropic is a paid third party like every other one. Before this,
        # ALLOW_PAID_CALLS guarded Apify, Perplexity and MillionVerifier while
        # the two model stages billed real tokens the moment LLM_FAKE was
        # unset, which is 22% of a 3,300-lead run's cost sitting outside every
        # gate the runbook advertises.
        require_paid(
            "anthropic:%s" % model, len(batch),
            llm.estimate_cost(model, TOKENS_IN_PER_BUSINESS * len(batch), TOKENS_OUT_PER_BUSINESS * len(batch)),
            "ICP scoring bills real tokens. Set LLM_FAKE=1 for a rehearsal.",
        )
    raw = llm.complete(role, SYSTEM, build_prompt(batch, rubric), max_tokens=min(4000, 120 * len(batch) + 300),
                       json_mode=True, model=model)
    parsed = _parse_results(raw, len(batch))
    if parsed is None:
        logger.warning("ICP batch of %d got an unusable response from %s; all unsure", len(batch), model)
        return [{"verdict": VERDICT_UNSURE, "confidence": 0.0, "reason": "model response unusable"}
                for _ in batch]
    for row in parsed:
        row["model"] = model
    return parsed


# --------------------------------------------------------------- offline fake
# Without this, an LLM_FAKE run falls back to the library's generic fake, whose
# answer does not parse, so every business the keyword rules could not settle
# comes back "unsure" and is rejected. A rehearsal then only ever exercises the
# rule layer and says nothing about the model layer. This stand-in scores from
# the same accept/reject signal lists the prompt shows the model, which is
# deterministic, offline and free. Same shape as
# services.reply_engine.classify.install_offline_fakes.
def offline_score(system: str, user: str, json_mode: bool) -> Dict[str, Any]:
    results = []
    for line in (user or "").splitlines():
        stripped = line.strip()
        if not stripped or not stripped[0].isdigit() or ". " not in stripped:
            continue
        number, _, body = stripped.partition(". ")
        try:
            n = int(number)
        except ValueError:
            continue
        low = body.lower()
        accepts = _signals(user, "Counts as a match:")
        rejects = _signals(user, "Does NOT count:")
        # keyword_hit, not ``in``: the same substring bug lives here, and a
        # rehearsal that quietly rejects "warehouse cleaning" as "house
        # cleaning" reports a pass rate the real model would not produce.
        hits = sum(1 for word in accepts if keyword_hit(low, word))
        misses = sum(1 for word in rejects if keyword_hit(low, word))
        if hits and hits > misses:
            results.append({"n": n, "verdict": VERDICT_ACCEPT,
                            "confidence": min(0.95, 0.7 + 0.08 * hits), "reason": "offline: %d accept signals" % hits})
        elif misses:
            results.append({"n": n, "verdict": VERDICT_REJECT, "confidence": 0.9,
                            "reason": "offline: %d reject signals" % misses})
        else:
            results.append({"n": n, "verdict": VERDICT_UNSURE, "confidence": 0.3, "reason": "offline: no signal"})
    return {"results": results}


def _signals(prompt: str, header: str) -> List[str]:
    for line in (prompt or "").splitlines():
        if line.startswith(header):
            return [part.strip().lower() for part in line[len(header):].split(",") if part.strip()]
    return []


def offline_fakes_wanted() -> bool:
    return llm.is_fake() and os.environ.get("LIST_FACTORY_OFFLINE_FAKES", "1") == "1"


def install_offline_fakes() -> None:
    """Register the offline scorer for roles that have nothing registered.

    A role a test deliberately faked is left alone, so a test can still pin an
    exact model answer.
    """
    if not offline_fakes_wanted():
        return
    for role in ("icp_score", "icp_escalate"):
        if llm.fake_for(role) is None:
            llm.register_fake(role, offline_score)


if offline_fakes_wanted():
    install_offline_fakes()


def score(
    leads: List[Dict[str, Any]],
    rubric: Dict[str, Any],
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_escalations: int = DEFAULT_MAX_ESCALATIONS,
    on_batch: Optional[Any] = None,
) -> Dict[str, Any]:
    """Score every lead in place. Returns a summary.

    Each lead gets ``icp_verdict``, ``icp_confidence``, ``icp_reason`` and
    ``icp_decided_by`` (``rule``, the Haiku model id, or the escalation model
    id). Rejections are applied by the caller so this stays a pure scorer.
    """
    summary = {
        "scored": 0, "rule_accept": 0, "rule_reject": 0,
        "model_calls": 0, "escalations": 0,
        "accept": 0, "reject": 0, "unsure_rejected": 0,
    }
    min_confidence = float(rubric.get("min_confidence") or 0.7)
    escalate_below = float(rubric.get("escalate_below") or 0.8)
    classify_model = llm.model_for("classify")
    escalate_model = llm.model_for("escalate")

    undecided = []  # type: List[Dict[str, Any]]
    for lead in leads:
        summary["scored"] += 1
        verdict = rule_verdict(lead, rubric)
        if verdict["verdict"] == VERDICT_REJECT:
            lead["icp_verdict"] = VERDICT_REJECT
            lead["icp_confidence"] = 1.0
            lead["icp_reason"] = verdict["reason"]
            lead["icp_decided_by"] = "rule"
            summary["rule_reject"] += 1
            summary["reject"] += 1
            continue
        if verdict["verdict"] == VERDICT_ACCEPT:
            lead["icp_verdict"] = VERDICT_ACCEPT
            lead["icp_confidence"] = 1.0
            lead["icp_reason"] = verdict["reason"]
            lead["icp_decided_by"] = "rule"
            summary["rule_accept"] += 1
            summary["accept"] += 1
            continue
        undecided.append(lead)

    for start in range(0, len(undecided), max(1, batch_size)):
        batch = undecided[start:start + max(1, batch_size)]
        results = score_batch(batch, rubric, model=classify_model)
        summary["model_calls"] += 1
        for lead, result in zip(batch, results):
            verdict = result["verdict"]
            confidence = result.get("confidence") or 0.0
            decided_by = result.get("model") or classify_model
            needs_escalation = (
                verdict == VERDICT_UNSURE
                or (verdict == VERDICT_ACCEPT and confidence < escalate_below)
            )
            if needs_escalation and summary["escalations"] < max_escalations:
                summary["escalations"] += 1
                summary["model_calls"] += 1
                escalated = score_batch([lead], rubric, model=escalate_model, role="icp_escalate")
                if escalated:
                    result = escalated[0]
                    verdict = result["verdict"]
                    confidence = result.get("confidence") or 0.0
                    decided_by = escalate_model
            lead["icp_verdict"] = verdict
            lead["icp_confidence"] = confidence
            lead["icp_reason"] = result.get("reason") or ""
            lead["icp_decided_by"] = decided_by
            if verdict == VERDICT_ACCEPT and confidence >= min_confidence:
                summary["accept"] += 1
            elif verdict == VERDICT_ACCEPT:
                # Accepted, but not confidently enough to mail. Treated as a
                # reject and counted separately so the rubric can be tuned.
                lead["icp_verdict"] = VERDICT_REJECT
                lead["icp_reason"] = "accept below min_confidence %.2f: %s" % (min_confidence, lead["icp_reason"])
                summary["reject"] += 1
            elif verdict == VERDICT_UNSURE:
                lead["icp_verdict"] = VERDICT_REJECT
                lead["icp_reason"] = "unsure: %s" % (lead["icp_reason"] or "no evidence")
                summary["unsure_rejected"] += 1
                summary["reject"] += 1
            else:
                summary["reject"] += 1
        if on_batch is not None:
            on_batch(len(batch))
    return summary
