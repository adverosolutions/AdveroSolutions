"""The three lessons and the three bets: prompt, rubric, and the judge that
throws out everything the rubric does not accept.

This is the only expensive model call in the whole system (``role="retro"`` ->
Opus 5, Blueprint O6, once a week). It is also the only place where the packet
stops reporting and starts asserting, so the rubric is deliberately harsh: a
lesson is rejected unless it names a number that actually moved this week,
quotes that number exactly as the packet prints it, points at a specific change
that plausibly caused it, and ends in an action with an owner and either a
target number or a date.

Generic advice is the failure mode this exists to stop. "Keep doing what is
working", "double down on cleaning", "continue to monitor deliverability" are
all rejected, by name, with a reason that is printed in the packet. Lorenzo
should be able to see the rubric working, so rejected proposals are rendered in
an appendix rather than silently dropped.

Nothing here talks to the network: ``propose()`` takes a ``complete`` callable
(``shared.llm.complete`` by default), so tests run it with a fake.
"""
import json
import logging
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("services.retro.lessons")

MAX_CALLS = 2  # one proposal, one repair. Never more: this model is expensive.
WANTED = 3

# Phrases that mark a sentence as advice rather than a decision. Matched against
# the next action and against a lesson that carries no number of its own.
GENERIC_PATTERNS = (
    r"\bkeep (doing|going|it up|pushing)\b",
    r"\bcontinue (to|with|doing)\b",
    r"\bstay (consistent|the course|focused)\b",
    r"\bdouble down\b",
    r"\bbest practice",
    r"\bit is important\b",
    r"\bmake sure to\b",
    r"\bconsider (testing|trying|adding|exploring)\b",
    r"\bmonitor (closely|it|this|performance)\b",
    r"\bkeep an eye\b",
    r"\bmaintain momentum\b",
    r"\b(test|try) more\b",
    r"\bin general\b",
    r"\bgoing forward\b",
    r"\bleverage\b",
    r"\bbe patient\b",
    r"\bas needed\b",
    r"\bwhere possible\b",
    r"\bscale up\b(?!.*\d)",
    # "Hold it above 1200" and "Review sent again next Friday" are restatement
    # with a number stapled on. They read the same in any week of any business,
    # which is the definition the rubric uses, and the number in them fooled the
    # NUMBER check. The package's own "compliant" fixture was made of these,
    # so the suite was pinning the advice the rubric exists to reject.
    r"\bhold it (at or )?above\b",
    r"\bhold [^.]{0,40}at or above\b",
    r"\breview [^.]{0,40}again next (friday|week)\b",
    r"\bhold [^.]{0,40}at this week's level\b",
)
GENERIC = [re.compile(p, re.I) for p in GENERIC_PATTERNS]

# Metrics where up is bad. The rubric had no notion of direction, so it
# accepted "Hold bounced above 17 next Friday" as a lesson and
# {"bet": "Push bounces to 40 next week", "metric": "bounced"} as a bet, and
# the Skool draft rendered "Next week: hold bounced at or above this week's
# level (17 or better)" as a public commitment to bounce more email.
LOWER_IS_BETTER = ("bounced", "bounce_rate", "no_shows", "negative", "unsubscribed")
RAISE_PATTERNS = (
    r"\bhold [^.]{0,40}\b(above|at or above|or better|or higher|at this week)",
    r"\bhold it (at or )?above\b",
    r"\b(raise|increase|grow|push|lift|bump|drive|boost) [^.]{0,40}\b(to|above|up|higher|by)\b",
    r"\bat or above\b",
    r"\bor better\b",
    r"\bor higher\b",
    r"\bkeep [^.]{0,40}\babove\b",
    r"\bmore\b",
)
RAISE = [re.compile(p, re.I) for p in RAISE_PATTERNS]

# Words too common to prove that a cause is talking about the thing it cites.
CITE_STOPWORDS = frozenset((
    "this", "that", "with", "from", "into", "week", "weeks", "have", "been", "were", "they",
    "them", "when", "what", "which", "after", "before", "moved", "moves", "change", "changed",
    "changes", "rate", "rates", "reply", "replies", "sent", "email", "emails", "lead", "leads",
    "campaign", "campaigns", "2026", "2025", "over", "under", "more", "less", "than", "shipped",
    "because", "since", "while", "about", "their", "there", "these", "those",
))
CITE_TOKEN = re.compile(r"[a-z0-9_]{4,}")

NUMBER = re.compile(r"\d")
DATE = re.compile(r"\b(20\d\d-\d\d-\d\d|mon|tue|wed|thu|fri|sat|sun)", re.I)
# A next action has to start with a verb. This is the crude but effective test:
# the first word is not "we", "the", "there", "it", "maybe".
WEAK_OPENERS = ("we", "the", "there", "it", "this", "that", "maybe", "perhaps", "i think")

DEFAULT_OWNERS = ("Lorenzo",)

RUBRIC = """A lesson is accepted only if all four hold:
1. NUMBER. It names one metric from the funnel table that moved this week, and
   quotes that metric's value exactly as the table prints it.
2. CAUSE. It names the specific change that plausibly moved it, and cites it:
   a commit hash from the system-changes list, a campaign key, an inbox domain,
   or a call item as "recap:<index>". A cause nobody can look up is not a cause,
   and the sentence itself must talk about the thing it cites: it has to repeat
   at least one distinctive word from the commit subject, the campaign name or
   the call item. "Emails sent moved to 1200 this week", citing a campaign, is
   a restatement of the number with a citation stapled to it, not a cause.
3. ACTION. It ends in one instruction that starts with a verb, has a named
   owner, and carries either a target number or a date.
4. NOT GENERIC. Advice that would read the same in any week of any business is
   rejected: keep doing what works, double down, continue to monitor, consider
   testing more, stay consistent, hold it above N, review it again next Friday.
5. DIRECTION. Bounces, bounce rate, no-shows and negative replies are metrics
   where up is bad. An action or a target that asks to hold, raise or beat one
   of them is rejected.

A bet is accepted only if it names an owner, a target containing a number, the
funnel metric it will be measured by, and a date inside next week, and it obeys
rule 5."""


class Rejection(object):
    def __init__(self, kind, index, reason, raw):
        # type: (str, int, str, Any) -> None
        self.kind = kind
        self.index = index
        self.reason = reason
        self.raw = raw

    def as_dict(self):
        return {"kind": self.kind, "index": self.index, "reason": self.reason, "raw": self.raw}

    def __repr__(self):
        return "Rejection(%s#%s, %s)" % (self.kind, self.index, self.reason)


# ------------------------------------------------------------------ context
def _norm_number(text):
    # type: (Any) -> str
    return re.sub(r"[\s,+]", "", str(text or "")).lower().lstrip("+")


def metric_number_variants(metric, fmt_number, fmt_delta):
    # type: (Any, Callable, Callable) -> List[str]
    """Every spelling of this metric's numbers the rubric will accept."""
    out = []
    for value in (metric.this_week, metric.last_week):
        if value is None:
            continue
        out.append(fmt_number(value, metric.unit))
        out.append(str(value))
        try:
            out.append("%g" % float(value))
        except (TypeError, ValueError):
            pass
    delta = fmt_delta(metric.this_week, metric.last_week, metric.unit)
    if delta not in ("not available", "flat", "new"):
        out.append(delta)
    return [_norm_number(v) for v in out if v]


def build_context(funnel, moved_keys, changes, recap_items, campaign_rows, thresholds,
                  fmt_number, fmt_delta, owners=DEFAULT_OWNERS):
    # type: (List[Any], List[str], List[Dict[str, str]], List[Dict[str, Any]], List[List[Any]], List[str], Callable, Callable, Tuple) -> Dict[str, Any]
    """Everything the model may use, and everything the judge will check against."""
    metrics = {}
    numbers = {}
    for metric in funnel:
        metrics[metric.key] = {
            "label": metric.label,
            "this_week": fmt_number(metric.this_week, metric.unit),
            "last_week": fmt_number(metric.last_week, metric.unit),
            "change": fmt_delta(metric.this_week, metric.last_week, metric.unit),
            "available": metric.available,
            "alert": metric.alert or "",
        }
        numbers[metric.key] = metric_number_variants(metric, fmt_number, fmt_delta)
    refs = set()
    cite_tokens = {}  # type: Dict[str, List[str]]

    def remember(ref, *texts):
        ref = ref.lower()
        refs.add(ref)
        bucket = set(cite_tokens.get(ref) or [])
        bucket.add(ref)
        for text in texts:
            for token in CITE_TOKEN.findall(str(text or "").lower()):
                if token not in CITE_STOPWORDS:
                    bucket.add(token)
        cite_tokens[ref] = sorted(bucket)

    for commit in changes or []:
        full = commit.get("hash") or ""
        if full:
            remember(full, commit.get("subject"))
            remember(full[:7], commit.get("subject"))
    for row in campaign_rows or []:
        if row and row[0]:
            remember(str(row[0]), row[0])
    for index, item in enumerate(recap_items or []):
        remember("recap:%d" % index, item.get("text"), item.get("subsection"))
    return {
        "metrics": metrics,
        "numbers": numbers,
        "moved": list(moved_keys or []),
        "refs": sorted(refs),
        # ref -> the distinctive words that prove a cause is about that ref.
        "cite_tokens": cite_tokens,
        "lower_is_better": list(LOWER_IS_BETTER),
        "changes": [
            {"hash": (c.get("hash") or "")[:7], "subject": c.get("subject"), "date": c.get("date")}
            for c in (changes or [])
        ],
        "recap_items": [
            {"index": i, "text": item.get("text"), "section": item.get("section")}
            for i, item in enumerate(recap_items or [])
        ],
        "campaigns": campaign_rows or [],
        "thresholds": thresholds or [],
        "owners": list(owners),
    }


# ------------------------------------------------------------------- prompts
SYSTEM = (
    "You are writing the data section of a weekly retro for a one-person cold-email agency. "
    "You report what the numbers did and what to do next. You never give generic business "
    "advice, you never invent a number, and you never name a cause that is not in the inputs. "
    "Everything you write is read by the owner, Lorenzo, and then acted on, so an action you "
    "cannot measure next Friday is worthless.\n\n" + RUBRIC
)

USER_TEMPLATE = """Here is the week.

FUNNEL (metric key -> value this week, value last week, change):
{metrics}

METRICS THAT MOVED (you may only write a lesson about one of these): {moved}

SYSTEM CHANGES THIS WEEK (cite by the 7-character hash):
{changes}

PER-CAMPAIGN (name, sent, real replies, real reply rate, then the same for last week):
{campaigns}

CALL ITEMS FROM THE WEEK (cite by index as "recap:<index>"):
{recaps}

SECTION 6 THRESHOLDS IN PLAY:
{thresholds}

VALID CITATIONS: {refs}
THE CAUSE MUST REPEAT A WORD FROM WHATEVER IT CITES. A sentence that only says the
number moved is not a cause, however correct the citation is.
METRICS WHERE UP IS BAD (never ask to hold or raise one of these): {lower_is_better}
VALID OWNERS: {owners}
NEXT WEEK RUNS {next_week_start} TO {next_week_end}.

Return JSON:
{{"lessons": [{{"metric": "<key>", "number": "<exactly as printed above>",
   "cause": "<one sentence>", "cite": "<hash or campaign name or recap:N>",
   "action": "<imperative sentence with a target number or a date>",
   "owner": "<owner>"}}],
 "bets": [{{"bet": "<one sentence>", "owner": "<owner>", "target": "<number and unit>",
   "metric": "<funnel key it is measured by>", "by": "<YYYY-MM-DD inside next week>"}}],
 "wins": [{{"text": "<one sentence>", "cite": <recap index int>}}],
 "objections": [{{"text": "<one sentence>", "cite": <recap index int>}}]}}

Exactly {wanted} lessons and {wanted} bets. Wins and objections only if a call item supports
them; an empty list is the correct answer when the week had no calls."""


def build_user(context, next_week_start, next_week_end, wanted=WANTED):
    # type: (Dict[str, Any], str, str, int) -> str
    metrics_lines = []
    for key, data in context["metrics"].items():
        metrics_lines.append("- %s (%s): this week %s, last week %s, change %s%s" % (
            key, data["label"], data["this_week"], data["last_week"], data["change"],
            ("  [ALERT: %s]" % data["alert"]) if data["alert"] else "",
        ))
    changes_lines = [
        "- %s %s (%s)" % (c["hash"], c["subject"], (c.get("date") or "")[:10])
        for c in context["changes"]
    ] or ["- (no commits in the window)"]
    campaign_lines = ["- %s" % " | ".join(str(cell) for cell in row) for row in context["campaigns"]] \
        or ["- (no per-campaign data)"]
    recap_lines = [
        "- recap:%d [%s] %s" % (r["index"], r.get("section") or "", r.get("text") or "")
        for r in context["recap_items"]
    ] or ["- (no call items this week)"]
    return USER_TEMPLATE.format(
        metrics="\n".join(metrics_lines),
        moved=", ".join(context["moved"]) or "(nothing moved)",
        changes="\n".join(changes_lines),
        campaigns="\n".join(campaign_lines),
        recaps="\n".join(recap_lines),
        thresholds="\n".join("- %s" % t for t in context["thresholds"]) or "- (none)",
        refs=", ".join(context["refs"]) or "(none)",
        lower_is_better=", ".join(context.get("lower_is_better") or LOWER_IS_BETTER),
        owners=", ".join(context["owners"]),
        next_week_start=next_week_start,
        next_week_end=next_week_end,
        wanted=wanted,
    )


# -------------------------------------------------------------------- judge
def is_generic(text):
    # type: (str) -> Optional[str]
    for pattern in GENERIC:
        if pattern.search(text or ""):
            return pattern.pattern
    return None


def asks_to_raise(text):
    # type: (str) -> Optional[str]
    """The pattern matched when a sentence asks for MORE of something."""
    for pattern in RAISE:
        if pattern.search(text or ""):
            return pattern.pattern
    return None


def cause_is_grounded(cause, cite, context):
    # type: (str, str, Dict[str, Any]) -> bool
    """True when the cause repeats a distinctive word from the thing it cites.

    A citation on its own proves nothing: "Emails sent moved to 1200 this week"
    with cite "2026 cleaning - trigger outbound" passed every other rule and is
    a tautology pointing at an unrelated campaign. The cause has to mention the
    commit, the campaign or the call item it blames.
    """
    tokens = (context.get("cite_tokens") or {}).get(cite)
    if not tokens:
        # Nothing to match against (an older context, or a ref with no words in
        # it): fall back to the citation rule alone rather than rejecting.
        return True
    lowered = (cause or "").lower()
    return any(token in lowered for token in tokens)


def validate_lesson(lesson, context):
    # type: (Dict[str, Any], Dict[str, Any]) -> List[str]
    """Reasons this lesson fails the rubric. Empty list means accepted."""
    reasons = []
    if not isinstance(lesson, dict):
        return ["not an object"]
    key = str(lesson.get("metric") or "").strip()
    if key not in context["metrics"]:
        reasons.append("metric %r is not in the funnel table" % key)
    elif key not in context["moved"]:
        reasons.append("metric %r did not move this week" % key)

    number = _norm_number(lesson.get("number"))
    if not number:
        reasons.append("no number quoted")
    elif key in context["numbers"] and number not in context["numbers"][key]:
        reasons.append(
            "number %r is not a value the table prints for %s (allowed: %s)"
            % (lesson.get("number"), key, ", ".join(context["numbers"][key][:4]))
        )

    cause = str(lesson.get("cause") or "").strip()
    if len(cause) < 12:
        reasons.append("no cause given")
    cite = str(lesson.get("cite") or "").strip().lower()
    if not cite:
        reasons.append("cause cites nothing")
    elif context["refs"] and cite not in context["refs"]:
        reasons.append("citation %r is not a commit, campaign or call item from this week" % cite)
    elif len(cause) >= 12 and not cause_is_grounded(cause, cite, context):
        reasons.append(
            "the cause does not mention what it cites (%r): say what changed, not what the "
            "number did" % cite)

    action = str(lesson.get("action") or "").strip()
    if len(action) < 10:
        reasons.append("no next action")
    else:
        first = action.split()[0].lower().rstrip(",")
        if first in WEAK_OPENERS:
            reasons.append("the action does not start with a verb")
        if not NUMBER.search(action) and not DATE.search(action):
            reasons.append("the action has no target number and no date")
        generic = is_generic(action)
        if generic:
            reasons.append("the action is generic advice (matched %s)" % generic)
        if key in LOWER_IS_BETTER:
            raising = asks_to_raise(action)
            if raising:
                reasons.append(
                    "%s is a metric where up is bad, and the action asks to hold or raise it "
                    "(matched %s)" % (key, raising))
    owner = str(lesson.get("owner") or "").strip()
    if owner not in context["owners"]:
        reasons.append("owner %r is not one of %s" % (owner, ", ".join(context["owners"])))

    blob = " ".join([cause, action])
    if not NUMBER.search(blob):
        generic = is_generic(blob)
        if generic:
            reasons.append("generic advice with no number (matched %s)" % generic)
    return reasons


def validate_bet(bet, context, next_week_dates):
    # type: (Dict[str, Any], Dict[str, Any], List[str]) -> List[str]
    reasons = []
    if not isinstance(bet, dict):
        return ["not an object"]
    if len(str(bet.get("bet") or "").strip()) < 10:
        reasons.append("no bet stated")
    owner = str(bet.get("owner") or "").strip()
    if owner not in context["owners"]:
        reasons.append("owner %r is not one of %s" % (owner, ", ".join(context["owners"])))
    target = str(bet.get("target") or "").strip()
    if not target:
        reasons.append("no target")
    elif not NUMBER.search(target):
        reasons.append("target %r has no number in it" % target)
    metric = str(bet.get("metric") or "").strip()
    if metric not in context["metrics"]:
        reasons.append("metric %r is not in the funnel table, so the bet cannot be scored" % metric)
    by = str(bet.get("by") or "").strip()[:10]
    if by not in next_week_dates:
        reasons.append("date %r is not inside next week (%s to %s)"
                       % (by, next_week_dates[0] if next_week_dates else "?",
                          next_week_dates[-1] if next_week_dates else "?"))
    generic = is_generic(str(bet.get("bet") or ""))
    if generic:
        reasons.append("the bet is generic advice (matched %s)" % generic)
    if metric in LOWER_IS_BETTER:
        raising = asks_to_raise("%s %s" % (bet.get("bet") or "", target))
        if raising:
            reasons.append(
                "%s is a metric where up is bad, and the bet asks to hold or raise it "
                "(matched %s)" % (metric, raising))
    return reasons


def validate_citation(item, recap_items):
    # type: (Dict[str, Any], List[Dict[str, Any]]) -> List[str]
    if not isinstance(item, dict):
        return ["not an object"]
    if len(str(item.get("text") or "").strip()) < 8:
        return ["no text"]
    cite = item.get("cite")
    try:
        index = int(cite)
    except (TypeError, ValueError):
        return ["cite %r is not a call item index" % cite]
    if index < 0 or index >= len(recap_items or []):
        return ["cite %d is outside the week's call items" % index]
    return []


# ------------------------------------------------------------------ propose
def _judge(payload, context, next_week_dates, recap_items):
    # type: (Dict[str, Any], Dict[str, Any], List[str], List[Dict[str, Any]]) -> Dict[str, Any]
    accepted_lessons = []
    accepted_bets = []
    wins = []
    objections = []
    rejections = []  # type: List[Rejection]
    for index, lesson in enumerate(payload.get("lessons") or []):
        reasons = validate_lesson(lesson, context)
        if reasons:
            rejections.append(Rejection("lesson", index, "; ".join(reasons), lesson))
        else:
            accepted_lessons.append(lesson)
    for index, bet in enumerate(payload.get("bets") or []):
        reasons = validate_bet(bet, context, next_week_dates)
        if reasons:
            rejections.append(Rejection("bet", index, "; ".join(reasons), bet))
        else:
            accepted_bets.append(bet)
    for kind, bucket, target in (("win", payload.get("wins") or [], wins),
                                 ("objection", payload.get("objections") or [], objections)):
        for index, item in enumerate(bucket):
            reasons = validate_citation(item, recap_items)
            if reasons:
                rejections.append(Rejection(kind, index, "; ".join(reasons), item))
            else:
                enriched = dict(item)
                enriched["source"] = recap_items[int(item["cite"])]
                target.append(enriched)
    return {"lessons": accepted_lessons, "bets": accepted_bets, "wins": wins,
            "objections": objections, "rejections": rejections}


def _repair_prompt(user, result, wanted):
    # type: (str, Dict[str, Any], int) -> str
    lines = ["", "Your previous answer was judged against the rubric and these were rejected:"]
    for rejection in result["rejections"]:
        lines.append("- %s #%d: %s" % (rejection.kind, rejection.index, rejection.reason))
    lines.append("")
    lines.append(
        "Replace only the rejected items. Keep the %d lessons and %d bets that were accepted. "
        "Return the same JSON shape with exactly %d lessons and %d bets."
        % (len(result["lessons"]), len(result["bets"]), wanted, wanted)
    )
    return user + "\n".join(lines)


def propose(context, next_week_dates, recap_items, complete=None, wanted=WANTED, max_calls=MAX_CALLS):
    # type: (Dict[str, Any], List[str], List[Dict[str, Any]], Optional[Callable], int, int) -> Dict[str, Any]
    """Ask the expensive model once (twice at most) and judge every item.

    Returns {lessons, bets, wins, objections, rejections, calls, short}. ``short``
    is True when the rubric could not be satisfied; the packet prints what was
    accepted and the appendix of what was not, rather than padding.
    """
    if complete is None:
        from shared.llm import complete as llm_complete  # local import keeps this module pure
        complete = llm_complete

    user = build_user(context, next_week_dates[0] if next_week_dates else "",
                      next_week_dates[-1] if next_week_dates else "", wanted)
    calls = 0
    best = {"lessons": [], "bets": [], "wins": [], "objections": [], "rejections": []}
    prompt = user
    while calls < max_calls:
        calls += 1
        try:
            raw = complete("retro", SYSTEM, prompt, max_tokens=2000, json_mode=True)
        except Exception as exc:  # noqa: BLE001 - a failed retro must not kill the packet
            logger.warning("retro model call failed: %s", exc)
            best["error"] = str(exc)[:300]
            break
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except ValueError:
                best["error"] = "model did not return JSON"
                break
        result = _judge(raw or {}, context, next_week_dates, recap_items)
        # Keep whichever attempt accepted more.
        if (len(result["lessons"]), len(result["bets"])) >= (len(best["lessons"]), len(best["bets"])):
            best = result
        if len(result["lessons"]) >= wanted and len(result["bets"]) >= wanted:
            break
        if calls >= max_calls:
            break
        prompt = _repair_prompt(user, result, wanted)
    best["calls"] = calls
    best["short"] = len(best["lessons"]) < wanted or len(best["bets"]) < wanted
    best["rejections"] = [r.as_dict() if isinstance(r, Rejection) else r for r in best["rejections"]]
    return best
