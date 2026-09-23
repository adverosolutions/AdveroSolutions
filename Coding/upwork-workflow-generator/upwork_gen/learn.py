"""Promote a compiler-authored spec into the vault, so the miss becomes a hit.

Every compiler run costs a model turn — call it ninety seconds. Every vault hit
costs six milliseconds. The only thing standing between the two is that the
classifier has never seen the posting shape before, so promotion has two halves
and both are mandatory:

1. **The spec file**, written to `vault/archetypes/`.
2. **Keywords in `vault/keywords.json`**, derived from the job post that
   produced it. Without these the archetype exists but can never be matched,
   which is worse than not promoting at all — it looks like coverage and
   behaves like a gap.

Keywords are mined from the posting rather than the spec, because the
classifier reads postings. Terms already claimed by another archetype are
dropped, so a new entry cannot quietly start stealing traffic from a
hand-tuned one.
"""

from __future__ import annotations

import datetime
import json
import os
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from .spec import WorkflowSpec, slugify

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VAULT_DIR = os.path.join(ROOT, "vault", "archetypes")
KEYWORDS_PATH = os.path.join(ROOT, "vault", "keywords.json")

# Spec fields that describe one client's build and never enter the vault.
CLIENT_SPECIFIC_FIELDS = ("client", "config", "overview")

# The 20 seed archetypes are hand-tuned; promotion never overwrites them
# without --force, because a learned entry replacing a curated one is a silent
# quality regression.
SEED_ARCHETYPES = {
    "ai_content_publish", "ai_rag_chatbot", "alert_approval", "api_etl",
    "booking_calendar", "cold_email_sequencer", "crm_sync", "doc_generation",
    "ecommerce_order", "invoice_ocr", "lead_capture_enrich_crm", "messaging_bot",
    "multi_agent_ops", "payment_onboarding", "reporting_digest", "resume_screening",
    "social_repurpose", "ticket_triage", "voice_ai_call", "web_monitoring",
}

# Ordinary English plus the boilerplate every Upwork post contains. A term that
# appears in all postings distinguishes none of them.
_STOP = set("""
a an and are as at be been being but by can could did do does for from get got had has have
he her him his how i if in into is it its just like me more most my no nor not of off on once
only or other our out over own same she should so some such than that the their them then
there these they this those to too under until up very was we were what when where which
while who whom why will with would you your yours able about after all also any because before
both each few many much need needs other own several through
looking need needed needs want wants seeking hire hiring freelancer contractor candidate
project work working job role position apply application applicants please include experience
experienced expert help build building create creating make making set setup use using
years year long term great good best strong excellent must plus bonus ideal ideally
business company team our us we're we are you'll your rate hourly budget availability
tools tool platform platforms solution solutions system systems process processes
automate automation automations workflow workflows task tasks time save saving
""".split())

_TOKEN = re.compile(r"[a-z][a-z0-9\.\-\+]{1,}")

# Almost every posting ends with instructions to the applicant. That tail
# describes the hiring process, not the work, and mining it yields terms like
# "become long-term" and "agencies examples" that would match half of Upwork.
_APPLICATION_TAIL = re.compile(
    r"\b(to apply|when applying|how to apply|please include|please share|please provide"
    r"|in your (?:proposal|application|reply|response)|your proposal should"
    r"|to be considered|include the following|answer the following"
    r"|start your (?:proposal|application)|applicants? (?:must|should))\b",
    re.I,
)


def _tokens(text: str) -> List[str]:
    return [t.strip(".-+") for t in _TOKEN.findall(text.lower())]


def _strip_jd_header(text: str) -> str:
    """Drop the pipeline's jd.txt header before mining.

    `jobs/<slug>/jd.txt` is `url: ...`, the title, a metadata paragraph (rate,
    client record, connects), a blank line, then the post. Only the title and
    the post describe the work; the metadata mined terms like "nevada timezone"
    and "hires invites" that would match any future header.
    """
    lines = text.splitlines()
    if lines and lines[0].lower().startswith("url:"):
        lines = lines[1:]
    blank = next((i for i, line in enumerate(lines[:15]) if not line.strip()), None)
    if blank is not None and blank >= 2:
        lines = [lines[0]] + lines[blank:]
    return "\n".join(lines)


def _describes_the_work(text: str) -> str:
    """Drop the application-instructions tail before mining terms."""
    match = _APPLICATION_TAIL.search(text)
    return text[: match.start()] if match else text


def _existing_terms(exclude: Optional[str] = None) -> Set[str]:
    """Every literal term already claimed by a classifier profile.

    `exclude` skips the archetype being re-promoted. Without it, a second
    promotion of the same archetype treats its own keywords as taken and falls
    back to whatever weak terms are left — quietly degrading a good match into
    a bad one.
    """
    from .classify import ARCHETYPES

    claimed: Set[str] = set()
    for archetype in ARCHETYPES:
        if exclude and str(archetype.get("id")) == exclude:
            continue
        for pattern, _weight in archetype["kw"]:  # type: ignore[index]
            # Strip regex metacharacters down to the literal words inside.
            for word in re.split(r"[^a-z0-9\.\+]+", str(pattern).lower()):
                if len(word) > 2:
                    claimed.add(word)
    return claimed


def derive_keywords(job_text: str, limit: int = 10,
                    exclude: Optional[str] = None) -> List[Tuple[str, float]]:
    """Mine distinctive terms from a job posting.

    Bigrams are preferred over single words: "cold chain" identifies a posting
    shape, "chain" on its own collides with LangChain and blockchain work.
    """
    body = _describes_the_work(_strip_jd_header(job_text))
    # The headline names the job. Counting it twice lets the actual subject
    # outrank whatever the body happens to repeat.
    headline = body.strip().split("\n", 1)[0]
    body = "{}\n{}".format(headline, body)

    words = [w for w in _tokens(body) if w not in _STOP and len(w) > 2]
    claimed = _existing_terms(exclude)

    unigrams: Dict[str, int] = {}
    for word in words:
        unigrams[word] = unigrams.get(word, 0) + 1

    bigrams: Dict[str, int] = {}
    raw = [w for w in _tokens(body) if len(w) > 2]
    for i in range(len(raw) - 1):
        first, second = raw[i], raw[i + 1]
        if first in _STOP and second in _STOP:
            continue
        if first in _STOP or second in _STOP:
            continue
        bigrams["{} {}".format(first, second)] = bigrams.get("{} {}".format(first, second), 0) + 1

    scored: List[Tuple[float, str]] = []
    for phrase, count in bigrams.items():
        if any(part in claimed for part in phrase.split()):
            continue
        scored.append((count * 2.5, phrase))
    for word, count in unigrams.items():
        if word in claimed:
            continue
        scored.append((float(count), word))

    scored.sort(key=lambda kv: (-kv[0], kv[1]))
    top = scored[:limit]
    if not top:
        return []

    # Normalise into the 1.5-2.5 band the hand-tuned profiles use, so a learned
    # entry competes on equal footing rather than dominating by sheer weight.
    peak = top[0][0] or 1.0
    out: List[Tuple[str, float]] = []
    for score, phrase in top:
        weight = 1.5 + (score / peak) * 1.0
        out.append((re.escape(phrase), round(weight, 2)))
    return out


def load_learned() -> Dict[str, Any]:
    if not os.path.exists(KEYWORDS_PATH):
        return {}
    try:
        with open(KEYWORDS_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (ValueError, OSError):
        return {}
    return {k: v for k, v in data.items() if not k.startswith("_")}


def _save_learned(data: Dict[str, Any]) -> None:
    payload = {
        "_note": "Written by `upwork_gen spec --jd`. Keywords are mined from the "
                 "job posting that produced each archetype; classify.py merges "
                 "these with its built-in profiles at import.",
    }
    payload.update(data)
    with open(KEYWORDS_PATH, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)


def promote(spec: WorkflowSpec, job_text: Optional[str] = None,
            archetype_id: Optional[str] = None, force: bool = False) -> Dict[str, Any]:
    """Write the spec into the vault and teach the classifier to find it.

    Returns a report dict; raises nothing the caller cannot recover from, since
    a failed promotion must never cost a generation that already succeeded.
    """
    archetype_id = archetype_id or spec.archetype or slugify(spec.title, 48).replace("-", "_")

    if archetype_id in SEED_ARCHETYPES and not force:
        return {
            "promoted": False,
            "archetype": archetype_id,
            "reason": "{!r} is a hand-tuned seed archetype; pass --force to replace it".format(
                archetype_id
            ),
        }

    if not os.path.isdir(VAULT_DIR):
        os.makedirs(VAULT_DIR)

    # Stamp the id back onto the in-memory spec, not just the file written
    # below. Everything downstream — corpus tagging, source archiving — reads
    # `spec.archetype`, and a spec authored without one would otherwise be
    # promoted with keywords but no archived source, leaving those keywords
    # impossible to re-derive later.
    spec.archetype = archetype_id

    existed = os.path.exists(os.path.join(VAULT_DIR, "{}.json".format(archetype_id)))

    payload = spec.to_dict()
    # An archetype is reused for every future client, so what was written for
    # this one stays behind: their name and company (client), their settings
    # (config) and the overview sticky's bullets (overview), which quote their
    # words. Node labels, params and system messages are the spec author's
    # content and are kept as written.
    for key in CLIENT_SPECIFIC_FIELDS:
        payload.pop(key, None)
    payload["archetype"] = archetype_id
    payload["learned"] = True
    payload["learned_at"] = datetime.date.today().isoformat()
    with open(os.path.join(VAULT_DIR, "{}.json".format(archetype_id)), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)

    keywords: List[Tuple[str, float]] = []
    if job_text:
        keywords = derive_keywords(job_text, exclude=archetype_id)

    learned = load_learned()
    learned[archetype_id] = {
        "label": spec.title,
        "kw": [[pattern, weight] for pattern, weight in keywords],
        "learned_at": datetime.date.today().isoformat(),
    }
    _save_learned(learned)

    return {
        "promoted": True,
        "archetype": archetype_id,
        "replaced": existed,
        "keywords": [re.sub(r"\\(.)", r"\1", k) for k, _ in keywords],
        "reachable": bool(keywords),
    }
