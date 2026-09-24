"""Run gate + extract over collected posts, with a price tag first.

Paid calls need ALLOW_PAID_CALLS=1 (the list factory's switch, same
semantics) unless LLM_FAKE is on. ``estimate`` prices a run without calling
anything; the job's ``--preflight`` prints it and exits. Every billed call
still goes through shared/llm.py's spend ceiling.

A post is re-analyzed only when its text changed (a new author reply), so a
weekly run pays for new and young posts, not the whole archive.
"""
import hashlib
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from shared import llm

from services.offer_intel import extract as extract_mod
from services.offer_intel import files
from services.offer_intel import gate as gate_mod

logger = logging.getLogger("offer_intel.analyze")

TRUTHY = ("1", "true", "yes", "on", "y", "t")
WIN_SHARE_GUESS = 0.6  # share of wins-category posts that are real business wins, until measured


class PaidCallsOff(Exception):
    pass


def paid_allowed() -> bool:
    return llm.is_fake() or os.environ.get("ALLOW_PAID_CALLS", "").strip().lower() in TRUTHY


def source_hash(record: Dict[str, Any]) -> str:
    return hashlib.sha1(gate_mod.source_text(record).encode("utf-8")).hexdigest()[:16]


def pending(records: Iterable[Dict[str, Any]], force: bool = False) -> List[Dict[str, Any]]:
    out = []
    for record in records:
        done = files.load_analyzed(record["post_id"])
        if force or not done or done.get("source_hash") != source_hash(record):
            out.append(record)
    return out


def newest_first(records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(records, key=lambda r: str(r.get("created_at") or ""), reverse=True)


def estimate(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Typical and worst-case USD for gating every post and extracting the
    expected share of wins (worst case: every post is a win, every call runs
    to max_tokens, every gate escalates)."""
    gate_model = llm.model_for("classify")
    esc_model = llm.model_for("escalate")
    ext_model = llm.model_for("research")
    typical = worst = 0.0
    for record in records:
        text = gate_mod.source_text(record)
        gate_in = (len(gate_mod.SYSTEM) + len(text)) // 4
        ext_in = (len(extract_mod.SYSTEM + extract_mod.JSON_ONLY) + len(text)) // 4
        typical += llm.estimate_cost(gate_model, gate_in, gate_mod.TYPICAL_OUT_TOKENS)
        typical += WIN_SHARE_GUESS * llm.estimate_cost(ext_model, ext_in, extract_mod.TYPICAL_OUT_TOKENS)
        worst += llm.projected_cost_usd(gate_model, gate_mod.SYSTEM, text, gate_mod.MAX_TOKENS)
        worst += llm.projected_cost_usd(esc_model, gate_mod.SYSTEM, text, gate_mod.MAX_TOKENS)
        worst += llm.projected_cost_usd(ext_model, extract_mod.SYSTEM + extract_mod.JSON_ONLY, text,
                                       extract_mod.MAX_TOKENS)
    return {"posts": len(records), "typical_usd": round(typical, 4), "worst_usd": round(worst, 4),
            "models": {"gate": gate_model, "escalate": esc_model, "extract": ext_model},
            "win_share_guess": WIN_SHARE_GUESS}


def analyze_one(record: Dict[str, Any], now: Optional[datetime] = None) -> Dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    verdict = gate_mod.gate(record)
    result = {"post_id": record["post_id"], "analyzed_at": now.isoformat(), "source_hash": source_hash(record),
              "gate": verdict, "extract": None}
    if verdict["is_win"]:
        result["extract"] = extract_mod.extract(record)
    return result


def run(records: List[Dict[str, Any]], now: Optional[datetime] = None) -> Dict[str, Any]:
    if not paid_allowed():
        raise PaidCallsOff("ALLOW_PAID_CALLS is not set; run with --preflight to see the price, then "
                           "ALLOW_PAID_CALLS=1 once Lorenzo has OK'd it")
    counts = {"analyzed": 0, "wins": 0, "not_wins": 0, "escalated": 0, "errors": 0, "fields_dropped": 0}
    errors = []
    status = "ok"
    for record in records:
        try:
            result = analyze_one(record, now)
        except llm.LLMBudgetExceeded as exc:
            status = "budget_stop"
            errors.append({"post_id": record["post_id"], "error": str(exc)[:300]})
            break
        except llm.LLMError as exc:
            counts["errors"] += 1
            errors.append({"post_id": record["post_id"], "error": str(exc)[:300]})
            continue
        files.save_analyzed(result)
        counts["analyzed"] += 1
        counts["wins" if result["gate"]["is_win"] else "not_wins"] += 1
        counts["escalated"] += 1 if result["gate"].get("escalated") else 0
        counts["fields_dropped"] += len(((result.get("extract") or {}).get("dropped") or {}))
    return {"status": status, "counts": counts, "errors": errors}
