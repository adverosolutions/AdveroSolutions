"""Staging the DAILY UPDATE post for Maker School.

The Skool MCP lives in a Claude session, not inside a job process, so this
module never talks to Skool over HTTP. It does three things:

1. builds the exact ``skool_posts_create`` arguments,
2. records them as a would_do in the shadow log (``job_log.shadow``), in every
   mode. It does NOT call ``settings.guard_write``: in live mode that opens a
   ``live_write_intent`` Job_Log row a post is expected to close, and this
   module never posts, so the row hung open on every live run,
3. writes the post to ``.tmp/skool_post_<date>.md`` and the MCP arguments to
   ``.tmp/skool_post_<date>.json`` so a session (or Lorenzo) can post it after
   reading it.

Even in live mode the job cannot post: it returns ``mcp_handoff`` and the file
paths. That is deliberate. The post is public writing under Lorenzo's name, and
the blueprint's own O4 line allows "post ... (or stage for review)".

Group: Maker School, slug ``maker-school``, groupId
``e256cd9ef1ac4dbe9197634db46e9e3b`` (read from skool_community_info,
read-only, 2026-09-22). ``skool_community_labels`` answered 401 on the same
pull, so the optional category ``label`` is left unset until a session with
working auth can read the label list.
"""
import logging
import os
from datetime import date
from typing import Any, Dict, Optional

from shared import settings
from shared.paths import tmp_file
from services.metrics.render import copy_violations

logger = logging.getLogger("services.metrics.skool")

GROUP_SLUG = os.environ.get("SKOOL_GROUP", "maker-school")
GROUP_ID_ENV = "SKOOL_GROUP_ID"
DEFAULT_GROUP_ID = "e256cd9ef1ac4dbe9197634db46e9e3b"


def group_id() -> str:
    return os.environ.get(GROUP_ID_ENV) or DEFAULT_GROUP_ID


def post_title(day: date) -> str:
    """No em dash: this is public copy."""
    return "Daily Update: %s %d, %d" % (day.strftime("%a, %b"), day.day, day.year)


def build_post(day: date, block: str, label: Optional[str] = None) -> Dict[str, Any]:
    """Exactly the arguments ``skool_posts_create`` accepts, and nothing else.

    The tool schema is ``additionalProperties: false``, so a convenience key
    such as the group slug would make a session's copy-paste of the staged
    arguments fail validation. The slug is recorded beside them instead."""
    payload = {
        "groupId": group_id(),
        "title": post_title(day),
        "content": block,
    }
    if label:
        payload["label"] = label
    return payload


def stage(day: date, block: str, payload: Dict[str, Any]) -> Dict[str, str]:
    """Write the post and its MCP arguments to .tmp for Lorenzo to read."""
    import json

    md_path = tmp_file("skool_post_%s.md" % day.isoformat())
    json_path = tmp_file("skool_post_%s.json" % day.isoformat())
    try:
        with open(md_path, "w", encoding="utf-8") as fh:
            fh.write(block.rstrip() + "\n")
        with open(json_path, "w", encoding="utf-8") as fh:
            json.dump({"tool": "skool_posts_create", "group_slug": GROUP_SLUG,
                       "arguments": payload}, fh, indent=1)
            fh.write("\n")
    except OSError as exc:
        logger.warning("could not stage the Skool post: %s", exc)
        return {}
    return {"markdown": str(md_path), "arguments": str(json_path)}


def post(day: date, block: str, label: Optional[str] = None) -> Dict[str, Any]:
    """Guarded. Never posts: returns the staged files and the guard record.

    A copy-rule breach blocks the post outright rather than staging text that
    breaks Lorenzo's voice."""
    violations = copy_violations(block)
    payload = build_post(day, block, label=label)
    if violations:
        logger.error("Skool post blocked by the copy rules: %s", ", ".join(violations))
        return {"ok": False, "reason": "copy_violation", "violations": violations,
                "staged": stage(day, block, payload)}
    from shared import job_log

    # A would_do, not a guarded write: nothing below posts, in any mode.
    record = job_log.shadow("skool", "posts_create", payload)
    staged = stage(day, block, payload)
    if not settings.is_live():
        return {"ok": True, "shadow": True, "posted": False, "reason": "shadow",
                "would_do": record, "staged": staged, "payload": payload}
    return {"ok": True, "shadow": False, "posted": False, "reason": "mcp_handoff",
            "detail": "the Skool MCP is only available inside a Claude session; "
                      "post the staged file after reading it",
            "would_do": record, "staged": staged, "payload": payload}
