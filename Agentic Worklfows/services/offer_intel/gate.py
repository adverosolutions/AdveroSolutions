"""Step 1 of analysis: is this post a business win, and which channel produced it?

Haiku (role ``classify``); below 0.8 confidence the same post goes to Sonnet
(role ``escalate``), per CLAUDE.md. Channel is what the post SAYS. The
community is about cold email, so the prompt forbids assuming it.
"""
import logging
from typing import Any, Dict

from shared import llm

logger = logging.getLogger("offer_intel.gate")

WIN_TYPES = ("first_client", "new_client", "revenue_milestone", "booked_calls", "reply_rate", "other_win")
CHANNELS = ("cold_email", "upwork", "linkedin", "referral", "cold_call", "ads", "content", "other", "unknown")
ESCALATE_BELOW = 0.8
MAX_TOKENS = 200
TYPICAL_OUT_TOKENS = 60
SOURCE_LIMIT = 6000

SYSTEM = """You sort posts from a paid online community whose members sell AI and automation services to businesses.

Decide whether the post reports a BUSINESS WIN: the author (or their agency) got a result from selling their service. Wins: a signed or paying client, revenue or a revenue milestone, a booked sales call or meeting, a cold email campaign result (replies, positive replies, meetings).
Not wins: course or learning progress, questions, motivation, a tool built for their own use, someone else's result, a job offer, an announcement.

Fields:
- is_win: true or false.
- win_type: one of first_client, new_client, revenue_milestone, booked_calls, reply_rate, other_win. Use other_win when is_win is false.
- channel: how the client or result came in, only as the post or the author's replies state it. One of cold_email, upwork, linkedin, referral, cold_call, ads, content, other, unknown. If the text does not say, answer unknown. Never assume cold_email because of what the community is about.
- confidence: 0 to 1.
- reason: at most 15 words.

Return JSON: {"is_win": ..., "win_type": "...", "channel": "...", "confidence": ..., "reason": "..."}"""


def source_text(record: Dict[str, Any], limit: int = SOURCE_LIMIT) -> str:
    """The text both steps read: title, post, and the author's own replies."""
    parts = ["POST ID: %s" % record.get("post_id"), "TITLE: %s" % (record.get("title") or "")]
    parts.append("POST:\n%s" % (record.get("content") or ""))
    replies = [r.get("content") for r in (record.get("author_replies") or []) if r.get("content")]
    if replies:
        parts.append("THE AUTHOR'S OWN REPLIES IN THE COMMENTS:\n" + "\n".join("- %s" % r for r in replies))
    text = "\n\n".join(parts)
    return text if len(text) <= limit else text[:limit] + "\n[cut]"


def _normalize(out: Any) -> Dict[str, Any]:
    out = out if isinstance(out, dict) else {}
    is_win = out.get("is_win")
    if isinstance(is_win, str):
        is_win = is_win.strip().lower() in ("true", "yes", "1")
    is_win = bool(is_win)
    win_type = str(out.get("win_type") or "").strip().lower()
    if not is_win or win_type not in WIN_TYPES:
        win_type = "other_win"
    channel = str(out.get("channel") or "").strip().lower().replace(" ", "_")
    if channel not in CHANNELS:
        channel = "unknown"
    try:
        confidence = max(0.0, min(1.0, float(out.get("confidence"))))
    except (TypeError, ValueError):
        confidence = 0.0
    return {"is_win": is_win, "win_type": win_type, "channel": channel, "confidence": confidence,
            "reason": str(out.get("reason") or "")[:200]}


def gate(record: Dict[str, Any]) -> Dict[str, Any]:
    user = source_text(record)
    first = _normalize(llm.complete("classify", SYSTEM, user, max_tokens=MAX_TOKENS, json_mode=True))
    first["model_role"] = "classify"
    first["escalated"] = False
    if first["confidence"] >= ESCALATE_BELOW:
        return first
    second = _normalize(llm.complete("escalate", SYSTEM, user, max_tokens=MAX_TOKENS, json_mode=True))
    second["model_role"] = "escalate"
    second["escalated"] = True
    second["first_pass"] = {k: first[k] for k in ("is_win", "channel", "confidence")}
    return second
