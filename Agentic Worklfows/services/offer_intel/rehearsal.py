"""Offline rehearsal: the whole pipeline on made-up posts, with no Skool, no
network and no billed model call.

Fixtures (jobs/tests/fixtures/offer_intel/):
    feed_page_*.json            pageProps of a wins category page (made-up members)
    post_<slug>.json            pageProps of one post page, full comment thread
    fake_model_responses.json   hand-written model answers keyed by post id. They
                                are NOT recordings of a real model; they exist to
                                exercise the gate, the escalation and the quote check
                                (two answers invent facts on purpose).
"""
import json
import re
from pathlib import Path
from typing import Any, Dict, List

from shared import llm
from shared.paths import BASE_DIR

from services.offer_intel import skool_read

FIXTURE_DIR = BASE_DIR / "jobs" / "tests" / "fixtures" / "offer_intel"
GROUP = "makerschool"
_POST_ID = re.compile(r"POST ID:\s*(\S+)")


def _load(path: Path) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def fixture_records(fixture_dir: Path = FIXTURE_DIR, stamp: str = "rehearsal") -> List[Dict[str, Any]]:
    """What ``collect`` would have saved: feed trees, upgraded with the full
    thread wherever a post page fixture exists."""
    records = {}  # type: Dict[str, Dict[str, Any]]
    for page in sorted(fixture_dir.glob("feed_page_*.json")):
        for tree in skool_read.trees_from_props(_load(page)):
            record = skool_read.record_from_tree(tree, GROUP, stamp)
            if record:
                records[record["post_id"]] = record
    for page in sorted(fixture_dir.glob("post_*.json")):
        for tree in skool_read.trees_from_props(_load(page)):
            record = skool_read.record_from_tree(tree, GROUP, stamp, thread_fetched=True)
            if record:
                records[record["post_id"]] = skool_read.merge_records(records.get(record["post_id"]), record)
    return list(records.values())


def install_fakes(fixture_dir: Path = FIXTURE_DIR) -> Dict[str, Any]:
    answers = _load(fixture_dir / "fake_model_responses.json")

    def answer_for(key: str, fallback_key: str = ""):
        def fn(system: str, user: str, json_mode: bool):
            match = _POST_ID.search(user or "")
            entry = answers.get(match.group(1), {}) if match else {}
            out = entry.get(key) or (entry.get(fallback_key) if fallback_key else None)
            if out is None:
                out = {"is_win": False, "win_type": "other_win", "channel": "unknown", "confidence": 0.9,
                       "reason": "no fake answer for this post"} if key.startswith("gate") else {}
            return out
        return fn

    llm.register_fake("classify", answer_for("gate"))
    llm.register_fake("escalate", answer_for("gate_escalate", "gate"))
    llm.register_fake("research", answer_for("extract"))
    return answers
