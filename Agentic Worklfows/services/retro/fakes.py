"""Offline stand-ins for the one expensive model call.

``LLM_FAKE=1`` makes ``shared.llm.complete`` return a canned answer, but the
built-in default for an unknown role is ``{"role": ..., "fake": True}``, which
carries no lessons and no bets, so every offline run of the retro would render
an empty packet and prove nothing. These fakes produce a **rubric-valid**
proposal derived from the real context, so an offline run shows the packet the
way a live run would fill it in.

``shared.llm.fake_for(role)`` is how a caller tells "nothing is registered" from
"a test registered its own": ``jobs/retro_packet`` only substitutes
``compliant`` when nothing else has claimed the role, so a test's fake always
wins. It substitutes it for the one call rather than registering it globally,
because a fake built from one week's context is wrong for the next one: a
second run in the same process reused the first run's next-week dates and every
bet in the second packet was rejected as "not inside next week".

``generic`` is the opposite fixture: the answer a lazy model gives. Every item
in it is rejected by the rubric, which is what the rubric test asserts.

``compliant`` used to be made entirely of the advice the rubric exists to
reject: causes that only restated the metric ("Emails sent moved to 1200 this
week") against an unrelated citation, and actions like "Review sent again next
Friday and hold it above 1200". It passed because the CAUSE rule was a length
check and the generic list had no pattern for restatement-with-a-number. The
rubric now checks that the cause repeats a word from what it cites and that no
action asks for more of a metric where up is bad, so this fixture states a real
cause and moves each metric in the direction that is good for it.
"""
import json
from typing import Any, Callable, Dict, List, Optional


def _cite_phrase(context, ref):
    # type: (Dict[str, Any], str) -> str
    """A few words from the cited object, so the cause is about the thing it
    cites and not about the metric restating itself."""
    tokens = [t for t in ((context.get("cite_tokens") or {}).get(ref) or []) if t != ref]
    if not tokens:
        return ref
    return " ".join(tokens[:3])


def _floored(key, value, lower_is_better):
    # type: (str, Any, Any) -> bool
    """A lower-is-better metric already at zero cannot be cut: the replay once
    accepted the bet "Cut bounced below 0"."""
    if key not in lower_is_better:
        return False
    try:
        return float(str(value).replace("%", "").replace(",", "").replace("$", "")) <= 0
    except (TypeError, ValueError):
        return False


def compliant(context, next_week_dates, recap_items=None, wanted=3):
    # type: (Dict[str, Any], List[str], Optional[List[Dict[str, Any]]], int) -> Callable
    """A fake that passes the rubric, built from the week actually collected."""
    recap_items = recap_items or []

    def fake(system, user, json_mode):
        from .lessons import LOWER_IS_BETTER

        moved = [k for k in context.get("moved") or [] if k in context.get("metrics", {})
                 and not _floored(k, context["metrics"][k].get("this_week"), LOWER_IS_BETTER)]
        refs = context.get("refs") or []
        owner = (context.get("owners") or ["Lorenzo"])[0]
        deadline = next_week_dates[4] if len(next_week_dates) > 4 else (
            next_week_dates[-1] if next_week_dates else "")
        lessons = []
        for index, key in enumerate(moved[:wanted]):
            data = context["metrics"][key]
            ref = refs[index % len(refs)] if refs else ""
            down = key in LOWER_IS_BETTER
            lessons.append({
                "metric": key,
                "number": data["this_week"],
                "cause": ("The work behind %s (%s) is what %s tracks, and it landed inside this "
                          "window" % (_cite_phrase(context, ref), ref, data["label"])),
                "cite": ref,
                "action": (("Cut %s below %s by %s" if down else "Take %s past %s by %s")
                           % (key, data["this_week"], deadline or "next Friday")),
                "owner": owner,
            })
        bets = []
        for index, key in enumerate(moved[:wanted]):
            data = context["metrics"][key]
            down = key in LOWER_IS_BETTER
            bets.append({
                "bet": (("Cut %s below %s next week" if down else "Take %s past %s next week")
                        % (key, data["this_week"])),
                "owner": owner,
                "target": (("under %s" if down else "past %s") % data["this_week"]),
                "metric": key,
                "by": deadline,
            })
        wins = []
        objections = []
        for index, item in enumerate(recap_items):
            tags = item.get("tags") or []
            if "win" in tags and len(wins) < 2:
                wins.append({"text": item.get("text", "")[:160], "cite": index})
            elif "open" in tags and len(objections) < 2:
                objections.append({"text": item.get("text", "")[:160], "cite": index})
        payload = {"lessons": lessons, "bets": bets, "wins": wins, "objections": objections}
        return payload if json_mode else json.dumps(payload)

    return fake


def generic(system, user, json_mode):
    """The answer the rubric exists to reject: advice with no number, no cause
    anyone can look up, and no owner."""
    payload = {
        "lessons": [
            {"metric": "vibes", "number": "", "cause": "things felt better",
             "cite": "", "action": "Keep doing what is working", "owner": ""},
            {"metric": "sent", "number": "999999", "cause": "we sent more emails",
             "cite": "nosuchcommit", "action": "Continue to monitor deliverability",
             "owner": "somebody"},
            {"metric": "real_reply_rate", "number": "1.00%", "cause": "copy",
             "cite": "recap:999", "action": "We should double down on cleaning",
             "owner": "Lorenzo"},
        ],
        "bets": [
            {"bet": "Do better next week", "owner": "Lorenzo", "target": "more",
             "metric": "sent", "by": "2099-01-01"},
        ],
        "wins": [{"text": "Everyone was happy", "cite": 9999}],
        "objections": [{"text": "Nothing", "cite": "not-an-index"}],
    }
    return payload if json_mode else json.dumps(payload)


def install_if_unclaimed(context, next_week_dates, recap_items=None):
    # type: (Dict[str, Any], List[str], Optional[List[Dict[str, Any]]]) -> bool
    """Register ``compliant`` for role "retro" unless something already is.

    Returns True when it installed one. Only ever called when LLM_FAKE is on.

    **The job no longer uses this**, because a global registration outlives the
    week it was built for (see the module docstring). It is kept for a replay
    or demo script that genuinely wants ``shared.llm.complete`` itself to
    answer, and such a caller must re-register per week.
    """
    from shared import llm

    if not llm.is_fake():
        return False
    if llm.fake_for("retro") is not None:
        return False
    llm.register_fake("retro", compliant(context, next_week_dates, recap_items))
    return True
