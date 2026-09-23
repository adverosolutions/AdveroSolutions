"""Parse Fireflies emails into the call material the retro quotes.

What Fireflies actually sends (read read-only from Lorenzo's Gmail on
2026-09-22, fixtures in ``fixtures/fireflies_emails_2026-09.json``):

1. "Your meeting recap - <meeting title>" from fred@fireflies.ai, one per call.
   **The body carries no notes.** The plaintext is a shell of table pipes and a
   link to app.fireflies.ai; the content lives behind the link in an HTML image
   block. There is nothing to quote. The parser records the meeting title, the
   time from the subject line and the recap URL, and marks it ``link_only``.
2. "Catch up on yesterday in 2 minutes" from fred@fireflies.ai, one per day.
   This is the Daily Brief and it is the one with the content: ACTION ITEMS,
   POPULAR TOPICS (with sub-headings), BLOCKERS and OPEN QUESTIONS, as ``*``
   bullets, each ending in a ``^1[](https://app.fireflies.ai/view/<id>)``
   citation. Empty sections read "No <thing> identified for today.".

So the week's wins and objections come from the Daily Briefs, and the recap
emails only prove which calls happened. That is a real limitation of the email
channel, not a parser bug: pulling the transcript itself needs the Fireflies
app or its API, which Lorenzo has not connected.

The job never calls Gmail. A Claude session with the Gmail connector stages the
raw messages as JSON (see runbooks/retro.md), exactly the way pipeline_sweep
reads ``.tmp/upwork_rooms.json`` for the Upwork MCP. Without that file the
section degrades and says so.
"""
import re
from typing import Any, Dict, List, Optional

FIREFLIES_SENDERS = ("fireflies.ai",)
DAILY_BRIEF_SUBJECTS = ("catch up on yesterday",)
RECAP_SUBJECTS = ("your meeting recap",)

# "No action items identified for today." and its siblings.
EMPTY_SENTINEL = re.compile(r"^no .{0,40}identified for (today|this period)\.?$", re.I)
# "^1[](https://app.fireflies.ai/view/01M2...)" trailing every bullet.
CITATION = re.compile(r"\s*\^\d+\s*\[\]\(([^)]*)\)")
MD_LINK = re.compile(r"\[([^\]]*)\]\(([^)]*)\)")
# Headings arrive glued to what follows them ("#### POPULAR TOPICS##### Commercial
# Terms * ..."), so a heading runs from the hashes to the first #, * or | and the
# level tells section (####, ALL CAPS) from subsection (#####, Title Case).
HEADING = re.compile(r"(#{4,5})[ \t]*([^#*|\n]+)")
SUBHEADING_LEVEL = 5

# Bullets that state something the prospect or client pushed back on, or that
# is still unresolved. Fireflies writes these as "Open: ..." inside a topic.
OPEN_PREFIX = re.compile(r"^open\s*:\s*", re.I)
# Deliberately narrow. These tags are a hint for the model and a deterministic
# fallback list, not the answer: a loose word like "competitor" tagged "weekly
# competitor scrape" as an objection, which is how a retro ends up quoting an
# objection nobody raised.
OBJECTION_WORDS = (
    "concern", "concerned", "worried", "hesitant", "push back", "pushback",
    "too expensive", "not sure", "objection", "blocker", "blocked", "hold off",
    "cheaper", "on the fence", "no budget",
)
WIN_WORDS = (
    "committed", "signed", "agreed", "paid", "payment", "retainer", "booked",
    "onboarding", "approved", "expansion", "referral", "renewal", "closed",
)


def _clean(text):
    # type: (str) -> str
    text = CITATION.sub("", text or "")
    text = MD_LINK.sub(lambda m: m.group(1), text)
    text = text.replace("|", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip(" .\u00a0\u034f\u200c-")


def _citation(text):
    # type: (str) -> Optional[str]
    match = CITATION.search(text or "")
    return match.group(1) if match else None


def is_fireflies(message):
    # type: (Dict[str, Any]) -> bool
    sender = str(message.get("sender") or message.get("from") or "").lower()
    return any(domain in sender for domain in FIREFLIES_SENDERS)


def kind_of(message):
    # type: (Dict[str, Any]) -> str
    subject = str(message.get("subject") or "").lower()
    if any(s in subject for s in DAILY_BRIEF_SUBJECTS):
        return "daily_brief"
    if any(s in subject for s in RECAP_SUBJECTS):
        return "meeting_recap"
    return "other"


def body_of(message):
    # type: (Dict[str, Any]) -> str
    return str(
        message.get("plaintextBody")
        or message.get("plaintext_body")
        or message.get("body")
        or ""
    )


def parse_daily_brief(message):
    # type: (Dict[str, Any]) -> Dict[str, Any]
    """One Daily Brief -> {date, sections: {HEADING: [item, ...]}, items: [...]}.

    An item is {text, section, subsection, url, tags}. ``tags`` is the
    deterministic first pass: "open" for an unresolved question, "objection"
    for pushback language, "win" for commitment language. The model may label
    further, but it may only cite items that are in this list.
    """
    body = body_of(message)
    out = {
        "id": message.get("id"),
        "date": str(message.get("date") or "")[:10],
        "subject": message.get("subject"),
        "kind": "daily_brief",
        "sections": {},
        "items": [],
    }  # type: Dict[str, Any]

    # Walk the headings in order; each one owns the text up to the next heading.
    section = None
    subsection = None
    matches = list(HEADING.finditer(body))
    for position, match in enumerate(matches):
        level = len(match.group(1))
        name = match.group(2).strip()
        if level >= SUBHEADING_LEVEL:
            subsection = name
        else:
            section = name
            subsection = None
            out["sections"].setdefault(section, [])
        if section is None:
            continue
        stop = matches[position + 1].start() if position + 1 < len(matches) else len(body)
        block = body[match.end():stop]
        for raw in block.split("*"):
            # The whole brief lives in one "| ... |" table cell, so anything
            # after a pipe is chrome ("View In App"), not part of the bullet.
            raw = raw.split("|")[0]
            text = _clean(raw)
            if not text or len(text) < 4:
                continue
            if EMPTY_SENTINEL.match(text):
                continue
            item = {
                "text": OPEN_PREFIX.sub("", text).strip(),
                "section": section,
                "subsection": subsection,
                "url": _citation(raw),
                "date": out["date"],
                "tags": [],
            }
            lowered = item["text"].lower()
            if OPEN_PREFIX.match(text) or section in ("OPEN QUESTIONS", "BLOCKERS"):
                item["tags"].append("open")
            if any(word in lowered for word in OBJECTION_WORDS):
                item["tags"].append("objection")
            if any(word in lowered for word in WIN_WORDS):
                item["tags"].append("win")
            out["sections"].setdefault(section, []).append(item)
            out["items"].append(item)
    return out


MEETING_TITLE = re.compile(r"your meeting recap\s*[-–—:]\s*(.+)$", re.I)
MEETING_WHEN = re.compile(r"([A-Z][a-z]{2} \d{1,2}(?:st|nd|rd|th)? at \d{1,2}:\d{2} [AP]M [A-Z]{3})")
RECAP_URL = re.compile(r"(https://app\.fireflies\.ai/view/[^\s)]+)")


def parse_meeting_recap(message):
    # type: (Dict[str, Any]) -> Dict[str, Any]
    body = body_of(message)
    subject = str(message.get("subject") or "")
    title = MEETING_TITLE.search(subject)
    when = MEETING_WHEN.search(body)
    url = RECAP_URL.search(body)
    return {
        "id": message.get("id"),
        "date": str(message.get("date") or "")[:10],
        "subject": subject,
        "kind": "meeting_recap",
        "title": title.group(1).strip() if title else subject,
        "when": when.group(1) if when else None,
        "url": url.group(1).split("?")[0] if url else None,
        # The email carries the link and nothing else; see the module docstring.
        "link_only": True,
        "items": [],
    }


def parse_messages(messages, window=None):
    # type: (Optional[List[Dict[str, Any]]], Optional[Any]) -> Dict[str, Any]
    """Parse a staged Gmail pull into the retro's call material.

    Returns {briefs, recaps, items, calls, note}. ``items`` is the flat, indexed
    list the model is allowed to cite; nothing else may appear in wins or
    objections.
    """
    out = {"briefs": [], "recaps": [], "items": [], "calls": [], "skipped": 0, "note": ""}
    for message in messages or []:
        if not is_fireflies(message):
            out["skipped"] += 1
            continue
        date = str(message.get("date") or "")[:10]
        if window is not None and not window.contains_date(date):
            out["skipped"] += 1
            continue
        kind = kind_of(message)
        if kind == "daily_brief":
            brief = parse_daily_brief(message)
            out["briefs"].append(brief)
            out["items"].extend(brief["items"])
        elif kind == "meeting_recap":
            recap = parse_meeting_recap(message)
            out["recaps"].append(recap)
            out["calls"].append({
                "date": recap["date"], "title": recap["title"],
                "when": recap["when"], "url": recap["url"],
            })
        else:
            out["skipped"] += 1
    for index, item in enumerate(out["items"]):
        item["index"] = index
    if out["recaps"] and not out["items"]:
        out["note"] = (
            "%d call recaps arrived this week but Fireflies recap emails carry only a link, "
            "no notes, and no Daily Brief in the window had content. Wins and objections are "
            "unavailable from email alone." % len(out["recaps"])
        )
    elif not out["briefs"] and not out["recaps"]:
        out["note"] = "no Fireflies emails in the window"
    elif out["briefs"] and not out["items"]:
        out["note"] = (
            "%d Fireflies Daily Briefs in the window, all of them empty "
            "(\"No action items identified for today\")" % len(out["briefs"])
        )
    return out


def tagged(items, tag):
    # type: (List[Dict[str, Any]], str) -> List[Dict[str, Any]]
    return [i for i in items or [] if tag in (i.get("tags") or [])]
