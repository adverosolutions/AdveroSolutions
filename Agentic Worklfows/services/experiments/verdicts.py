"""Campaign verdict rules and decision-date projection (Blueprint M4, brief A7).

The rules, verbatim from M4 and the A7 brief:

* No verdict before 1,000 sends.
* With at least one positive at 1,000, run to 3,000 before deciding.
* A variant is only judged at 500 sends or more per variant.
* Recruiting runs to 1,000 and, if still at zero positives, is proposed for
  retirement with its inboxes released.

Everything else here is the arithmetic those rules need, plus the Section 6
alert thresholds carried as flags (they never change the recommendation; they
travel with it so the Friday audit sees them in one table).

Nothing in this module talks to the network and nothing writes. It takes the
``CampaignStats`` objects ``analytics.collect()` produced and answers.
"""
import datetime
import logging
import math
from typing import Any, Dict, List, Optional

from shared import thresholds as TH

logger = logging.getLogger("services.experiments.verdicts")

# --- the M4 lines -----------------------------------------------------------
# Bound to shared/thresholds.py, the one home of every M4 and Section 6
# number. They were literals here (MKT-5); the names stay because the rest of
# this package and its tests read them.
VERDICT_LINE = TH.CAMPAIGN_VERDICT_MIN_SENDS          # 1,000: no verdict before this many sends
CONFIRM_LINE = TH.CAMPAIGN_CONFIRM_SENDS              # 3,000: with >=1 positive at 1,000, run to here
VARIANT_MIN_SENDS = TH.VARIANT_MIN_SENDS              # 500: a variant is judged only at or above this
REWORK_RETEST_LINE = TH.CAMPAIGN_REWORK_RETEST_SENDS  # 2,000: a reworked campaign gets another 1,000

# Niches whose zero-positive verdict at 1,000 is retirement rather than a copy
# rework. M4: "Recruiting - both ... Run to 1,000 only; zero positives and
# hostile replies. If still zero, retire and reuse the inboxes".
RETIRE_IF_ZERO_NICHES = ("recruiting",)

# --- Section 6 alert thresholds (flags, not verdicts) -----------------------
BOUNCE_ALERT = TH.BOUNCE_RATE_MAX_PCT / 100.0         # > 2% remove the inbox
REAL_REPLY_FLOOR = TH.REPLY_RATE_MIN_PCT / 100.0      # < 1% real replies
# Section 6 and M1 level 3 define the reply-rate line as "< 1% after 100 sent
# **per inbox**", measured off accounts/analytics/daily, and its remedy is
# removing an inbox from the campaign email_list. This module only has
# campaign-level numbers, so the same percentage is used as a *copy* signal and
# the sample gate is scaled by the inbox count: 12 inboxes means 1,200 campaign
# sends before 100-per-inbox is even possible. The per-inbox rule itself lives
# in jobs/deliverability_monitor.py, which reads the per-inbox endpoint.
MIN_SENDS_PER_INBOX_FOR_REPLY_CHECK = TH.REPLY_RATE_MIN_SENT
MIN_SENDS_FOR_REPLY_CHECK = TH.REPLY_RATE_MIN_SENT    # floor when the inbox count is unknown
POSITIVE_GREEN = TH.POSITIVE_REPLY_RATE_GREEN_PCT / 100.0   # >= 0.7% positive reply rate
POSITIVE_ALERT = TH.POSITIVE_REPLY_RATE_ALERT_PCT / 100.0   # < 0.5% for 3 days

# --- capacity -------------------------------------------------------------
# 12 active inboxes x 25 = 300/day today. 33 more inboxes (11 warming domains
# x the three lorenzo@ / lorenzov@ / lorenzovillarreal@ personas, ids.json
# instantly.warming_inboxes_note) go live 2026-10-11 for 45 x 25 = 1,125/day.
PERSONAS_PER_WARMING_DOMAIN = 3
CAPACITY_STEP_DATE = datetime.date(2026, 10, 11)

RECOMMENDATIONS = (
    "keep_running",   # below the verdict line, nothing to decide yet
    "run_to_3000",    # >=1 positive at 1,000
    "scale",          # proven at 3,000
    "hold",           # alive at 3,000 but not green; fix copy before adding volume
    "rework_copy",    # decided against at the line, but the niche is worth another pass
    "retire",         # decided against at the line; release the inboxes
)


class Capacity(object):
    """Workspace send capacity now and after the 2026-10-11 step."""

    def __init__(self, active_inboxes: int, warming_inboxes: int, per_inbox_daily_limit: int):
        self.active_inboxes = active_inboxes
        self.warming_inboxes = warming_inboxes
        self.per_inbox = per_inbox_daily_limit
        # Anything the reader has to know before believing the three ETA
        # columns. The report prints these above the tables; a logger.warning
        # on a cron run reaches nobody.
        self.notes = []  # type: List[str]

    @property
    def now_per_day(self) -> int:
        return self.active_inboxes * self.per_inbox

    @property
    def after_step_per_day(self) -> int:
        return (self.active_inboxes + self.warming_inboxes) * self.per_inbox

    @property
    def multiplier(self) -> float:
        """How much every campaign's daily rate grows on 2026-10-11, assuming
        the extra capacity is spread the way today's is. 1,125 / 300 = 3.75."""
        if not self.now_per_day:
            return 1.0
        return float(self.after_step_per_day) / float(self.now_per_day)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "active_inboxes": self.active_inboxes,
            "warming_inboxes": self.warming_inboxes,
            "per_inbox_daily_limit": self.per_inbox,
            "now_per_day": self.now_per_day,
            "after_2026_10_11_per_day": self.after_step_per_day,
            "multiplier": round(self.multiplier, 3),
            "notes": list(self.notes),
        }


def capacity_from_ids(ids: Dict[str, Any]) -> Capacity:
    inst = (ids or {}).get("instantly", {})
    active = len(inst.get("active_inboxes") or [])
    warming = len(inst.get("warming_domains") or []) * PERSONAS_PER_WARMING_DOMAIN
    per_inbox = int(inst.get("per_inbox_daily_limit") or 25)
    cap = Capacity(active, warming, per_inbox)
    if cap.now_per_day <= 0:
        # settings.load_ids() answers {} on FileNotFoundError and a renamed key
        # reads as an empty list, so this is what a broken config looks like:
        # every rate is 0, the multiplier is 1.0 and the three ETA columns
        # become the same number. Say so in the report, not only in the log.
        cap.notes.append(
            "config/ids.json lists no active inboxes, so today's capacity reads as 0/day. Every "
            "rate below falls back to each campaign's daily_limit and the three ETA columns are "
            "the same number. Check instantly.active_inboxes in ids.json before believing them.")
    if cap.now_per_day != 300 or cap.after_step_per_day != 1125:
        # Not an error: ids.json is the source of truth and Lorenzo buys
        # inboxes. Worth a line in the log because every projected date moves.
        message = (
            "capacity from ids.json is %d/day now and %d/day after %s; the blueprint was written "
            "against 300 and 1,125" % (cap.now_per_day, cap.after_step_per_day, CAPACITY_STEP_DATE))
        logger.warning("%s", message)
        cap.notes.append(message)
    return cap


# --------------------------------------------------------------- projections
def _sends_on(day: datetime.date, sending_days: Dict[str, Any]) -> bool:
    """`sending_days` is Instantly's `{"0": Sunday, ... "6": Saturday}` map."""
    key = str((day.weekday() + 1) % 7)  # Python Monday=0 -> Instantly Sunday=0
    return bool(sending_days.get(key, True))


def project_date(
    sent: int,
    target: int,
    start: datetime.date,
    sending_days: Dict[str, Any],
    per_day_now: int,
    per_day_after: Optional[int] = None,
    step_date: datetime.date = CAPACITY_STEP_DATE,
    max_days: int = 400,
) -> Optional[datetime.date]:
    """The date `sent` reaches `target`, counting only sending days.

    ``per_day_after`` (with ``step_date``) models the 2026-10-11 capacity
    step: days before the step date add ``per_day_now``, days from it add
    ``per_day_after``. Pass ``per_day_after=None`` for a flat rate.

    Returns None when the campaign is not sending (rate 0) or the target is
    further than ``max_days`` away, which is the honest answer for a paused
    campaign: "never at this rate", not a date 11 years out.
    """
    if sent >= target:
        return start
    if per_day_now <= 0 and (per_day_after is None or per_day_after <= 0):
        return None
    total = sent
    day = start
    for _ in range(max_days):
        if _sends_on(day, sending_days):
            rate = per_day_now
            if per_day_after is not None and day >= step_date:
                rate = per_day_after
            total += rate
            if total >= target:
                return day
        day = day + datetime.timedelta(days=1)
    return None


class Verdict(object):
    def __init__(self, stats, recommendation: str, reason: str, next_line: Optional[int]):
        self.key = stats.key
        self.stats = stats
        self.recommendation = recommendation
        self.reason = reason
        self.next_line = next_line          # the send count of the next decision point
        self.flags = []                     # type: List[str]
        self.eta_current = None             # type: Optional[datetime.date]
        self.eta_oct11 = None               # type: Optional[datetime.date]
        self.eta_blended = None             # type: Optional[datetime.date]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "campaign": self.key,
            "recommendation": self.recommendation,
            "reason": self.reason,
            "next_decision_point": self.next_line,
            "flags": list(self.flags),
            "eta_current_volume": self.eta_current.isoformat() if self.eta_current else None,
            "eta_oct11_volume": self.eta_oct11.isoformat() if self.eta_oct11 else None,
            "eta_blended": self.eta_blended.isoformat() if self.eta_blended else None,
            "stats": self.stats.to_dict(),
        }


def reply_check_minimum(stats) -> int:
    """Campaign sends needed before the real-reply percentage means anything.

    Section 6's line is 100 sent **per inbox**. Six campaigns share the same 12
    inboxes today, so a campaign at 300 sends has put at most 25 through each
    inbox: a quarter of the threshold's own precondition, on one reply. Scaling
    the gate by the inbox count is what keeps the flag off twelve healthy
    inboxes.
    """
    inboxes = getattr(stats, "inboxes", 0) or 0
    if inboxes <= 0:
        return MIN_SENDS_FOR_REPLY_CHECK
    return MIN_SENDS_PER_INBOX_FOR_REPLY_CHECK * inboxes


def section6_flags(stats) -> List[str]:
    """Alert thresholds from Blueprint Section 6. These never decide a verdict;
    they ride along so the Friday audit sees them in the same row.

    The real-reply flag is deliberately labelled campaign-level: the Section 6
    rule it echoes is per inbox and its remedy is removing an inbox, which this
    job must never suggest off a campaign-level number.
    """
    flags = []
    if stats.sent and stats.bounce_rate > BOUNCE_ALERT:
        flags.append("bounce %.1f%%, above the 2%% line" % (stats.bounce_rate * 100))
    minimum = reply_check_minimum(stats)
    if stats.sent >= minimum and stats.reply_rate < REAL_REPLY_FLOOR:
        flags.append(
            "campaign real reply %.2f%% over %d sends, below the 1%% line. This is a copy signal, "
            "not the Section 6 inbox rule: that one is 100 sent per inbox off "
            "accounts/analytics/daily and belongs to jobs/deliverability_monitor.py"
            % (stats.reply_rate * 100, stats.sent))
    if stats.sent >= VERDICT_LINE and stats.positive_rate < POSITIVE_ALERT:
        flags.append("positive reply %.2f%%, below the 0.5%% alert" % (stats.positive_rate * 100))
    if stats.partial:
        flags.append("replied-lead walk was truncated, so positives are a floor")
    if getattr(stats, "duplicate_leads", 0):
        flags.append("%d duplicate replied lead(s) dropped from the cursor walk"
                     % stats.duplicate_leads)
    if not getattr(stats, "is_active", True):
        flags.append("campaign is paused (status %s), so no ETA is projected"
                     % getattr(stats, "status", None))
    elif getattr(stats, "sends_nothing", False):
        flags.append("no sends in the pulled window although the campaign has sent before; "
                     "the rate is 0, not its daily limit")
    if getattr(stats, "closed_out", 0):
        flags.append("%d positive repl%s later closed out as lost or no-show; they still count as "
                     "positives for the copy verdict"
                     % (stats.closed_out, "y" if stats.closed_out == 1 else "ies"))
    if stats.positives == 0 and getattr(stats, "opportunities", 0):
        flags.append("Instantly reports %d opportunit%s but the replied-lead list carries zero "
                     "positives; the two disagree, so check the lead statuses before acting"
                     % (stats.opportunities, "y" if stats.opportunities == 1 else "ies"))
    if stats.negatives and not stats.positives:
        flags.append("%d negative repl%s and no positives"
                     % (stats.negatives, "y" if stats.negatives == 1 else "ies"))
    return flags


def released_capacity(stats, peers=None) -> Dict[str, Any]:
    """What retiring this campaign actually frees.

    All six live campaigns carry the **same** 12-inbox ``email_list``, so
    retiring one releases none of them: it releases that campaign's
    ``daily_limit`` of sending headroom. Saying "release its 12 inboxes" both
    overstates the dividend threefold and invites an operator to detach the 12
    inboxes that cleaning and bookkeeping are sending on.

    ``peers`` is the other campaigns' stats. Without them the exclusivity
    cannot be computed and the text says so rather than guessing.
    """
    mine = [e for e in (getattr(stats, "inbox_emails", None) or [])]
    limit = getattr(stats, "daily_limit", 0) or 0
    info = {
        "daily_limit_freed": limit,
        "inboxes": getattr(stats, "inboxes", 0) or 0,
        "exclusive_inboxes": None,
        "shared_with": None,
    }
    if peers is None or not mine:
        info["text"] = (
            "releases %d sends/day of daily_limit headroom. Its %d inboxes are shared across "
            "campaigns, so check the email_list overlap before detaching any"
            % (limit, info["inboxes"]))
        return info
    others = [p for p in peers if getattr(p, "key", None) != stats.key]
    union = set()
    sharers = 0
    for peer in others:
        peer_list = set(getattr(peer, "inbox_emails", None) or [])
        if peer_list & set(mine):
            sharers += 1
        union |= peer_list
    exclusive = sorted(set(mine) - union)
    info["exclusive_inboxes"] = len(exclusive)
    info["shared_with"] = sharers
    if exclusive:
        info["text"] = (
            "releases %d sends/day of daily_limit headroom and %d inbox(es) no other campaign uses "
            "(%d of its %d are shared with %d other campaign(s))"
            % (limit, len(exclusive), info["inboxes"] - len(exclusive), info["inboxes"], sharers))
    else:
        info["text"] = (
            "shares all %d of its inboxes with %d other campaign(s), so retiring it releases "
            "%d sends/day of daily_limit headroom and no inboxes"
            % (info["inboxes"], sharers, limit))
    return info


def decide(stats, retire_niches=RETIRE_IF_ZERO_NICHES, peers=None) -> Verdict:
    """Apply the M4 rules to one campaign.

    ``peers`` is every other campaign's stats, used only to say what retiring
    this one would actually free. Leave it out and the retirement text says the
    inbox overlap was not computed instead of claiming 12 inboxes.
    """
    retire_if_zero = stats.niche in retire_niches
    sent = stats.sent
    positives = stats.positives
    opportunities = getattr(stats, "opportunities", 0) or 0

    if sent < VERDICT_LINE:
        reason = "%d of %d sends; no verdict before the 1,000-send line" % (sent, VERDICT_LINE)
        if positives:
            reason += ". %d positive%s so far, so the 3,000-send confirmation run is already in play" % (
                positives, "" if positives == 1 else "s")
        elif retire_if_zero:
            reason += ". Zero positives so far, and at 1,000 with zero positives this campaign is " \
                      "proposed for retirement, %s" % released_capacity(stats, peers)["text"]
        verdict = Verdict(stats, "keep_running", reason, VERDICT_LINE)
    elif positives == 0 and opportunities:
        # The counted positives and Instantly's own opportunity counter
        # disagree. That is a data fault, not a dead campaign, and retiring on
        # it would release inboxes over a parsing bug.
        verdict = Verdict(
            stats, "hold",
            "%d sends and zero counted positives, but Instantly reports %d opportunit%s on this "
            "campaign. The two numbers disagree, so this is a data check for Lorenzo, not a "
            "retirement: read the lead statuses before deciding"
            % (sent, opportunities, "y" if opportunities == 1 else "ies"),
            None,
        )
    elif positives == 0:
        if retire_if_zero:
            verdict = Verdict(
                stats, "retire",
                "%d sends and zero positives. M4: run recruiting to 1,000 only, then retire it and "
                "give the capacity to the campaigns that convert. Retiring it %s"
                % (sent, released_capacity(stats, peers)["text"]),
                None,
            )
        elif sent >= REWORK_RETEST_LINE:
            # Past the re-test line with nothing to show. M4 stops at "re-test
            # to 2,000"; without this branch the campaign sits on rework_copy
            # for ever, pointed at a decision point it passed, while it eats
            # the capacity this engine exists to reallocate.
            verdict = Verdict(
                stats, "retire",
                "%d sends and still zero positives, past the %d-send re-test line. The rework had "
                "its 1,000 sends, so this goes to Lorenzo as a retirement proposal. Retiring it %s"
                % (sent, REWORK_RETEST_LINE, released_capacity(stats, peers)["text"]),
                None,
            )
        else:
            verdict = Verdict(
                stats, "rework_copy",
                "%d sends and zero positives, past the %d-send verdict line. The niche is not on "
                "the retire-at-1,000 list, so rewrite the offer sentence and the icebreaker and "
                "re-test to %d before retiring it" % (sent, VERDICT_LINE, REWORK_RETEST_LINE),
                REWORK_RETEST_LINE,
            )
    elif sent < CONFIRM_LINE:
        verdict = Verdict(
            stats, "run_to_3000",
            "%d sends with %d positive%s. M4: with at least one positive at 1,000, run to 3,000 "
            "before deciding" % (sent, positives, "" if positives == 1 else "s"),
            CONFIRM_LINE,
        )
    else:
        rate = stats.positive_rate
        if rate >= POSITIVE_GREEN:
            verdict = Verdict(
                stats, "scale",
                "%d sends, %d positives (%.2f%%), at or above the 0.7%% green line. Give it the "
                "largest share of the Oct 11 inboxes" % (sent, positives, rate * 100),
                None,
            )
        elif rate >= POSITIVE_ALERT:
            verdict = Verdict(
                stats, "hold",
                "%d sends, %d positives (%.2f%%), between the 0.5%% alert and 0.7%% green lines. "
                "Hold the current volume and fix the copy before adding inboxes"
                % (sent, positives, rate * 100),
                None,
            )
        else:
            verdict = Verdict(
                stats, "rework_copy",
                "%d sends, %d positives (%.2f%%), below the 0.5%% alert line. Rework the offer "
                "sentence before spending Oct 11 capacity on it" % (sent, positives, rate * 100),
                None,
            )
    verdict.flags = section6_flags(stats)
    return verdict


def post_step_rate(now_rate: int, capacity: Capacity, as_of: datetime.date) -> int:
    """The per-campaign rate once the 2026-10-11 inboxes are live.

    On or after the step date the observed rate **already contains** the step,
    so multiplying again projects 3.75x the workspace ceiling: at 188/campaign
    observed, a second multiply gives 705/campaign, 4,230/day across six
    campaigns against a real ceiling of 1,125. The multiplier is applied only
    while the step is still in the future.
    """
    if as_of >= CAPACITY_STEP_DATE:
        return now_rate
    return int(round(now_rate * capacity.multiplier))


def project(verdict: Verdict, capacity: Capacity, as_of: datetime.date) -> Verdict:
    """Fill the three decision dates on a verdict.

    ``eta_current``  the next line at today's rate, forever.
    ``eta_oct11``    the same line at the post-2026-10-11 rate, floored at the
                     step date itself: the "at the 2026-10-11 volume" column
                     the brief asks for. It is never earlier than 2026-10-11,
                     because that volume does not exist before then; printing
                     2026-09-25 under that header is a date that cannot happen.
    ``eta_blended``  today's rate until 2026-10-11 and the higher rate after:
                     the date to actually plan against.
    """
    if verdict.next_line is None:
        return verdict
    now_rate = verdict.stats.sends_per_day
    after_rate = post_step_rate(now_rate, capacity, as_of)
    days = verdict.stats.sending_days
    sent = verdict.stats.sent
    verdict.eta_current = project_date(sent, verdict.next_line, as_of, days, now_rate)
    oct11 = project_date(sent, verdict.next_line, as_of, days, after_rate)
    if oct11 is not None and oct11 < CAPACITY_STEP_DATE:
        oct11 = CAPACITY_STEP_DATE
    verdict.eta_oct11 = oct11
    verdict.eta_blended = project_date(
        sent, verdict.next_line, as_of, days, now_rate, per_day_after=after_rate
    )
    return verdict


def run(stats_by_key: Dict[str, Any], capacity: Capacity, as_of: datetime.date) -> Dict[str, Verdict]:
    if as_of > CAPACITY_STEP_DATE and capacity.warming_inboxes:
        note = (
            "it is past %s and config/ids.json still lists %d warming inboxes. If they went live, "
            "move them into instantly.active_inboxes: until then the capacity line below "
            "understates today and the Oct 11 column repeats it"
            % (CAPACITY_STEP_DATE.isoformat(), capacity.warming_inboxes))
        logger.warning("%s", note)
        if note not in capacity.notes:
            capacity.notes.append(note)
    peers = list(stats_by_key.values())
    out = {}
    for key, stats in stats_by_key.items():
        out[key] = project(decide(stats, peers=peers), capacity, as_of)
    return out


# ------------------------------------------------------------ variant tests
def _normal_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def two_proportion_p(x1: int, n1: int, x2: int, n2: int) -> Optional[float]:
    """Two-sided p-value for two proportions (pooled z). None when undefined.

    Hand-rolled because scipy is not installed and must not be. At the sample
    sizes this system reaches (500-3,000 sends, single-digit positives) the
    normal approximation is generous, so the caller treats a p-value as a
    tie-breaker on top of the 500-send rule, never as a licence to judge a
    variant below it.
    """
    if n1 <= 0 or n2 <= 0:
        return None
    p1 = float(x1) / n1
    p2 = float(x2) / n2
    pooled = float(x1 + x2) / float(n1 + n2)
    if pooled <= 0.0 or pooled >= 1.0:
        return None
    se = math.sqrt(pooled * (1.0 - pooled) * (1.0 / n1 + 1.0 / n2))
    if se == 0:
        return None
    z = (p1 - p2) / se
    return 2.0 * (1.0 - _normal_cdf(abs(z)))


class VariantVerdict(object):
    def __init__(self, campaign: str, step: int, status: str, reason: str):
        self.campaign = campaign
        self.step = step
        self.status = status        # single_variant | insufficient_sample | no_difference | winner
        self.reason = reason
        self.winner = None          # type: Optional[str]
        self.loser = None           # type: Optional[str]
        self.p_value = None         # type: Optional[float]
        self.cells = []             # type: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "campaign": self.campaign,
            "step": self.step,
            "status": self.status,
            "winner": self.winner,
            "loser": self.loser,
            "p_value": round(self.p_value, 4) if self.p_value is not None else None,
            "reason": self.reason,
            "cells": list(self.cells),
        }


def judge_step(stats, step_number: int, metric: str = "positives",
               alpha: float = TH.EXPERIMENT_ALPHA) -> VariantVerdict:
    """Judge the variants of one step. ``metric`` is "positives" (what M4 cares
    about) or "replies" (the larger, noisier number used when there are no
    positives yet to separate the arms)."""
    cells = stats.variants_for_step(step_number)
    vv = VariantVerdict(stats.key, step_number, "single_variant", "")
    vv.cells = [c.to_dict() for c in cells]
    if len(cells) < 2:
        vv.reason = "only one variant live on step %d; nothing to compare" % step_number
        return vv
    short = [c for c in cells if c.sent < VARIANT_MIN_SENDS]
    if short:
        need = ", ".join(["%s needs %d more sends" % (c.label, VARIANT_MIN_SENDS - c.sent) for c in short])
        vv.status = "insufficient_sample"
        vv.reason = "a variant is judged at %d sends or more; %s" % (VARIANT_MIN_SENDS, need)
        return vv
    getter = (lambda c: c.positives) if metric == "positives" else (lambda c: c.replies)
    ranked = sorted(cells, key=lambda c: (getter(c) / float(c.sent or 1), getter(c)), reverse=True)
    best, worst = ranked[0], ranked[-1]
    p = two_proportion_p(getter(best), best.sent, getter(worst), worst.sent)
    vv.p_value = p
    if p is None:
        vv.status = "no_difference"
        vv.reason = "no %s on either variant yet at %d and %d sends" % (metric, best.sent, worst.sent)
        return vv
    if p < alpha:
        vv.status = "winner"
        vv.winner = best.label
        vv.loser = worst.label
        vv.reason = "%s %d/%d beats %s %d/%d on %s, p=%.3f" % (
            best.label, getter(best), best.sent, worst.label, getter(worst), worst.sent, metric, p)
    else:
        vv.status = "no_difference"
        vv.reason = "%s %d/%d vs %s %d/%d on %s is not separable yet, p=%.3f" % (
            best.label, getter(best), best.sent, worst.label, getter(worst), worst.sent, metric, p)
    return vv


def judge_all_steps(stats, metric: str = "positives") -> List[VariantVerdict]:
    return [judge_step(stats, step, metric=metric) for step in stats.step_numbers]
