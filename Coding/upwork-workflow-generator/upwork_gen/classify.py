"""Job description -> platform, archetype, apps. No model in the loop.

Deliberately dumb and deliberately fast. Weighted keyword hits over twenty
archetype profiles, a platform sniff, and an app-name sweep. Runs in a few
milliseconds, has no API dependency, and — most usefully — returns MISS with an
honest confidence number when the posting does not look like anything in the
vault, which is the signal to hand the job to the LLM path instead of forcing a
bad archetype match.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# Confidence below this routes to Engine B rather than forcing a vault match.
MISS_THRESHOLD = 3.0

# --------------------------------------------------------------------------
# Platform detection
# --------------------------------------------------------------------------

_N8N_PAT = re.compile(r"\bn8n\b", re.I)
_MAKE_PAT = re.compile(r"\b(make\.com|make\s*\.\s*com|integromat|make\s+scenario|"
                       r"scenario\s+in\s+make|make\s+automation)\b", re.I)
_ZAPIER_PAT = re.compile(r"\bzapier\b", re.I)
_GHL_PAT = re.compile(r"\b(gohighlevel|go\s*high\s*level|highlevel|\bghl\b)\b", re.I)


def detect_platform(text: str) -> Tuple[str, str]:
    """Return (platform, reason). Ties break toward whichever is named first."""
    n8n_hits = _N8N_PAT.findall(text)
    make_hits = _MAKE_PAT.findall(text)

    if n8n_hits and not make_hits:
        return "n8n", "post names n8n"
    if make_hits and not n8n_hits:
        return "make", "post names Make.com"
    if n8n_hits and make_hits:
        # When a post accepts either, take n8n. Its importer is far more
        # forgiving, and an import that fails mid-recording costs more than
        # matching the client's incidental word order.
        if len(make_hits) >= 2 * len(n8n_hits):
            return "make", "both named, Make dominant"
        return "n8n", "both named — n8n chosen as the safer import"
    # Zapier and GoHighLevel have no import format, so there is no file to hand
    # over either way. n8n stays the build target because an importable prop
    # beats a picture, and these posts almost always tolerate it — but the
    # reason says so out loud, and `--platform zapier|gohighlevel` forces a
    # diagram-only run when a post is emphatic about one tool.
    if _GHL_PAT.search(text):
        return "n8n", ("post names GoHighLevel (no import format) — building n8n; "
                       "--platform gohighlevel for diagram-only")
    if _ZAPIER_PAT.search(text):
        return "n8n", ("post names Zapier (no import format) — building n8n; "
                       "--platform zapier for diagram-only")
    return "n8n", "no platform named — defaulting to n8n"


# --------------------------------------------------------------------------
# App extraction — names are the catalog's vocabulary, not display strings.
# --------------------------------------------------------------------------

APP_ALIASES: Dict[str, Tuple[str, ...]] = {
    "googleSheets": ("google sheet", "google sheets", "gsheet", "spreadsheet", "sheets"),
    "gmail": ("gmail", "google mail"),
    "slack": ("slack",),
    "airtable": ("airtable",),
    "hubspot": ("hubspot",),
    "notion": ("notion",),
    "telegram": ("telegram",),
    "whatsapp": ("whatsapp", "whats app"),
    "discord": ("discord",),
    "twilio": ("twilio", "sms"),
    "postgres": ("postgres", "postgresql", "supabase db"),
    "openai": ("openai", "gpt-4", "gpt4", "gpt-3", "chatgpt", "gpt"),
    "anthropic": ("claude", "anthropic"),
    "pinecone": ("pinecone",),
    "supabase": ("supabase",),
    "stripe": ("stripe",),
    "shopify": ("shopify",),
    "googleDrive": ("google drive", "gdrive"),
    "googleDocs": ("google doc", "google docs"),
    "googleCalendar": ("google calendar", "gcal"),
    "wordpress": ("wordpress", "wp "),
    "calendly": ("calendly",),
    "salesforce": ("salesforce",),
    "pipedrive": ("pipedrive",),
    "monday": ("monday.com", "monday board"),
    "clickup": ("clickup",),
    "instantly": ("instantly.ai", "instantly"),
    "apollo": ("apollo.io", "apollo"),
    "zoom": ("zoom",),
    "quickbooks": ("quickbooks", "qbo"),
    "xero": ("xero",),
}


def detect_apps(text: str) -> List[str]:
    """Apps named in the post, ordered by where they first appear.

    Order carries meaning. A post that says "push to Salesforce, log the rest in
    Airtable" names both, and the one mentioned first is the one meant for the
    primary role. Returning these in alias-table order instead would hand the
    CRM slot to whichever app happened to be listed first in this file.
    """
    lower = text.lower()
    hits: List[Tuple[int, str]] = []
    for app, aliases in APP_ALIASES.items():
        positions = [lower.find(alias) for alias in aliases if alias in lower]
        if positions:
            hits.append((min(positions), app))
    hits.sort()
    return [app for _, app in hits]


# --------------------------------------------------------------------------
# Archetype profiles. `kw` entries are (pattern, weight).
# --------------------------------------------------------------------------

ARCHETYPES: List[Dict[str, object]] = [
    {"id": "ai_rag_chatbot", "label": "AI chatbot / RAG over documents", "kw": [
        ("rag", 3), ("retrieval augmented", 3), ("vector (db|database|store)", 3),
        ("knowledge base", 2.5), ("chatbot", 2), ("embedding", 2), ("pinecone", 2),
        ("chat over", 2), ("answer questions", 1.5), ("document q", 2), ("semantic search", 2)]},

    {"id": "lead_capture_enrich_crm", "label": "Lead capture → enrich → CRM", "kw": [
        ("lead", 2), ("enrich", 3), ("crm", 2), ("qualif", 2.5), ("lead scor", 3),
        ("form submission", 2), ("inbound", 1.5), ("prospect", 1.5), ("route lead", 2)]},

    {"id": "cold_email_sequencer", "label": "Cold email / outreach sequencer", "kw": [
        ("cold email", 3), ("outreach", 2.5), ("email sequence", 3), ("drip", 2),
        ("follow[- ]?up email", 2), ("personaliz", 2), ("instantly", 2), ("smartlead", 2),
        ("apollo", 1.5), ("icebreaker", 2)]},

    {"id": "invoice_ocr", "label": "Invoice / receipt OCR → accounting", "kw": [
        ("invoice", 3), ("receipt", 3), ("ocr", 3), ("extract.*pdf", 2.5), ("bookkeep", 2),
        ("quickbooks", 2), ("xero", 2), ("accounts payable", 2.5), ("expense", 2)]},

    {"id": "social_repurpose", "label": "Social content repurposing", "kw": [
        ("repurpos", 3), ("clip", 2), ("short[- ]?form", 2.5), ("tiktok", 2), ("reels", 2),
        ("youtube", 1.5), ("transcri", 1.5), ("social media post", 2.5), ("caption", 1.5)]},

    {"id": "ai_content_publish", "label": "AI content generation → CMS", "kw": [
        ("blog post", 3), ("seo", 2.5), ("article", 2), ("wordpress", 2.5), ("content calendar", 2),
        ("publish", 1.5), ("copywriting", 2), ("generate content", 2.5)]},

    {"id": "crm_sync", "label": "Two-way CRM / database sync", "kw": [
        ("two[- ]way sync", 3), ("sync", 2.5), ("keep.*in sync", 3), ("mirror", 2),
        ("bidirectional", 3), ("airtable.*sheets|sheets.*airtable", 2.5), ("dedup", 2)]},

    {"id": "alert_approval", "label": "Alerting + human approval gate", "kw": [
        ("approval", 3), ("approve", 2.5), ("notify", 2), ("alert", 2.5), ("escalat", 2),
        ("slack notification", 2.5), ("human in the loop", 3), ("sign[- ]?off", 2)]},

    {"id": "ecommerce_order", "label": "E-commerce order → fulfillment", "kw": [
        ("shopify", 3), ("woocommerce", 3), ("order", 2), ("fulfillment", 3), ("shipping", 2),
        ("inventory", 2.5), ("abandoned cart", 2.5), ("tracking number", 2)]},

    {"id": "booking_calendar", "label": "Booking / calendar automation", "kw": [
        ("calendly", 2.5), ("booking", 2.5), ("appointment", 3), ("schedul.*meeting", 2.5),
        ("no[- ]?show", 2.5), ("reminder", 2), ("reschedul", 2.5), ("calendar", 2)]},

    {"id": "ticket_triage", "label": "Support ticket triage + auto-reply", "kw": [
        ("ticket", 3), ("support", 2), ("triage", 3), ("helpdesk", 3), ("zendesk", 2.5),
        ("intercom", 2.5), ("customer inquir", 2.5), ("auto[- ]?repl", 2.5), ("categoriz", 2)]},

    {"id": "api_etl", "label": "API ETL with pagination + retry", "kw": [
        ("etl", 3), ("pagination", 3), ("paginate", 3), ("rate limit", 2.5), ("retry", 2.5),
        ("data pipeline", 2.5), ("api integration", 2), ("bulk", 1.5), ("migrat", 2)]},

    {"id": "messaging_bot", "label": "WhatsApp / Telegram bot", "kw": [
        ("telegram", 3), ("whatsapp", 3), ("bot", 2), ("conversational", 2), ("chat bot", 2.5),
        ("twilio", 2), ("sms", 2)]},

    {"id": "resume_screening", "label": "Resume screening / candidate scoring", "kw": [
        ("resume", 3), ("cv ", 2.5), ("candidate", 3), ("applicant", 3), ("recruit", 2.5),
        ("screening", 2.5), ("ats", 2), ("hiring", 2)]},

    {"id": "reporting_digest", "label": "Scheduled reporting digest", "kw": [
        ("daily report", 3), ("weekly report", 3), ("digest", 3), ("dashboard", 2),
        ("summary email", 2.5), ("kpi", 2.5), ("metrics", 2), ("scheduled report", 3)]},

    {"id": "voice_ai_call", "label": "Voice AI call → transcript → CRM", "kw": [
        ("vapi", 3), ("retell", 3), ("voice ai", 3), ("call transcript", 3), ("phone call", 2),
        ("cold call", 2), ("transcription", 2.5), ("call summary", 3), ("voice agent", 3)]},

    {"id": "doc_generation", "label": "Form → generated document", "kw": [
        ("generate.*pdf", 3), ("proposal", 2), ("contract", 2.5), ("document generation", 3),
        ("template.*document", 2.5), ("docusign", 2.5), ("quote", 2), ("fill.*template", 2.5)]},

    {"id": "payment_onboarding", "label": "Payment → onboarding sequence", "kw": [
        ("stripe", 3), ("payment", 2.5), ("subscription", 2.5), ("onboard", 3), ("churn", 2),
        ("dunning", 2.5), ("new customer", 2), ("welcome sequence", 2.5)]},

    {"id": "web_monitoring", "label": "Web monitoring / scraping → alerts", "kw": [
        ("scrap", 3), ("monitor.*website", 3), ("price track", 3), ("change detect", 3),
        ("competitor", 2.5), ("crawl", 2.5), ("watch.*page", 2.5), ("alert.*change", 2.5)]},

    {"id": "multi_agent_ops", "label": "Multi-agent AI research crew", "kw": [
        ("multi[- ]?agent", 3), ("ai agent", 2.5), ("agentic", 3), ("crew", 2), ("orchestrat", 2.5),
        ("autonomous", 2.5), ("research agent", 3), ("tool call", 2), ("sub[- ]?agent", 2.5)]},
]


def _merge_learned() -> None:
    """Fold promoted archetypes into the profile list.

    Learned entries are data, not code, so promoting an archetype never needs a
    source edit. Imported lazily to avoid a circular import — learn.py reads
    ARCHETYPES to find which terms are already claimed.
    """
    from .learn import load_learned

    known = {str(a["id"]) for a in ARCHETYPES}
    for archetype_id, entry in sorted(load_learned().items()):
        if archetype_id in known or not entry.get("kw"):
            continue
        ARCHETYPES.append({
            "id": archetype_id,
            "label": entry.get("label", archetype_id),
            "kw": [(str(p), float(w)) for p, w in entry["kw"]],
            "learned": True,
        })


_merge_learned()


@dataclass
class Classification:
    platform: str
    platform_reason: str
    archetype: Optional[str]
    archetype_label: Optional[str]
    confidence: float
    is_miss: bool
    apps: List[str] = field(default_factory=list)
    runner_up: Optional[str] = None
    scores: List[Tuple[str, float]] = field(default_factory=list)

    @property
    def engine_hint(self) -> str:
        return "compiler" if self.is_miss else "vault"

    def summary(self) -> str:
        archetype = self.archetype_label or "no archetype match"
        return "{} · {} (confidence {:.1f}) · apps: {}".format(
            self.platform, archetype, self.confidence,
            ", ".join(self.apps) if self.apps else "none named",
        )


def _post_body(text: str) -> str:
    """A pipeline jd.txt (`url: ...`, title, metadata paragraph, blank, post)
    loses its metadata paragraph before scoring. That paragraph is the client's
    hiring history ("Shopify", "GHL pages"), and it was steering the platform,
    the apps and the archetype toward jobs this post is not. Plain post text
    (no `url:` first line) passes through untouched."""
    first = text.lstrip().split("\n", 1)[0]
    if not first.lower().startswith("url:"):
        return text
    from .learn import _strip_jd_header  # lazy: learn and classify import each other
    return _strip_jd_header(text.lstrip())


def classify(text: str) -> Classification:
    text = _post_body(text)
    lower = text.lower()
    scores: List[Tuple[str, float]] = []

    for archetype in ARCHETYPES:
        total = 0.0
        for pattern, weight in archetype["kw"]:  # type: ignore[index]
            hits = len(re.findall(pattern, lower))
            if hits:
                # Repeats signal emphasis, but with sharply diminishing returns
                # so one word repeated ten times cannot hijack the match.
                total += float(weight) * (1.0 + min(hits - 1, 3) * 0.25)
        scores.append((str(archetype["id"]), total))

    scores.sort(key=lambda kv: (-kv[1], kv[0]))
    best_id, best_score = scores[0]
    runner_up_id, runner_up_score = scores[1] if len(scores) > 1 else (None, 0.0)

    # A win that barely clears the runner-up is not a win. Treating an ambiguous
    # match as a miss is cheap; recording a Loom over the wrong workflow is not.
    ambiguous = runner_up_score > 0 and (best_score - runner_up_score) < 1.5
    is_miss = best_score < MISS_THRESHOLD or ambiguous

    label = None
    for archetype in ARCHETYPES:
        if archetype["id"] == best_id:
            label = str(archetype["label"])
            break

    platform, reason = detect_platform(text)
    return Classification(
        platform=platform,
        platform_reason=reason,
        archetype=None if is_miss else best_id,
        archetype_label=None if is_miss else label,
        confidence=best_score,
        is_miss=is_miss,
        apps=detect_apps(text),
        runner_up=runner_up_id,
        scores=scores[:5],
    )
