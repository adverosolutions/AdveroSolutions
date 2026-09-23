"""``config/experiments.json`` - every running copy test and where it stands.

One document, one list. Each record says what is being tested, what changed,
when it started, how much sample it needs, how much it has, and the result
once the rule can answer. ``jobs/campaign_verdicts.py`` refreshes the numbers
and flags winners and losers; nothing else writes the file.

Measurement kinds
-----------------
``campaign_variant``  the arms are Instantly variants of one step, so the
                      sample and the counters come straight from
                      ``GET /campaigns/analytics/steps`` and the replied-lead
                      list. This is the only kind the job can count on its own.
``lead_variable``     the arms are a property of the lead, not of the
                      campaign (which icebreaker style it got). Instantly has
                      no per-lead-variable analytics, so the job reports the
                      test as ``blocked`` with the reason until the list
                      factory writes the variable onto the leads and this file
                      names it. Reporting 0 out of 1,500 would read as "the
                      test is running and losing", which is worse than saying
                      it cannot be measured yet.

Statuses: ``planned`` (nothing sent yet), ``running``, ``blocked``,
``undecidable`` (every campaign carrying the test is paused, sends nothing or
sits at its M4 retirement line, so no sample can ever arrive), ``decided``. A
decided test keeps its record; it is history, not clutter.

Which campaigns a test is judged on
-----------------------------------
``sample_gate()`` leaves a campaign out of the decision, with the reason
recorded under ``sample_gate.excluded``, when it cannot keep gathering sample:
its campaign status is not active (paused or retired), it sent nothing in the
pulled window, or ``verdicts.decide`` puts it at ``retire``. Recruiting is the
case that forced this (owner decision R12, 2026-09-22): M4 runs it to 1,000
sends and then retires it, which is roughly 250 to 300 step-1 sends per
variant, so under "per arm, per campaign" a test that kept recruiting in scope
could never reach 500 on it and could never be decided. A left-out campaign's
numbers stay in ``observed_by_campaign`` for the record but do not count
toward the decision, on either side.

Two rules this file is easy to get wrong
----------------------------------------

**``sample_rule`` is read, not decoration.** ``sample_needed`` is per arm, and
``sample_rule`` says per *what*. "per arm, per campaign" (M3.3, and what
``verdicts.judge_step`` enforces) means every campaign running the test needs
500 sends on every arm: pooling six campaigns' step-1 cells and checking the
sum against 500 declares a winner on 83 sends per arm per campaign, across
three different niches. ``sample_gate()`` implements each rule explicitly and
refuses to decide a rule it does not implement.

**A decided test is frozen.** ``update()`` keeps refreshing the numbers, but
once ``result.decided_at`` is set the winner, loser, p-value and date stay put
and a later recomputation is written to ``post_decision`` instead. Without that
a Friday run with more sample flips a closed test back to ``running``, erases
the winner Lorenzo already acted on, and re-stamps ``decided_at`` with the
latest run date. Re-open a test by clearing ``result.decided_at`` by hand.
"""
import datetime
import json
import logging
import os
from typing import Any, Dict, List, Optional

from shared import thresholds as TH
from shared.paths import CONFIG_DIR

from services.experiments import verdicts as V

logger = logging.getLogger("services.experiments.experiment_log")

DEFAULT_PATH = str(CONFIG_DIR / "experiments.json")

STATUS_PLANNED = "planned"
STATUS_RUNNING = "running"
STATUS_BLOCKED = "blocked"
STATUS_DECIDED = "decided"
STATUS_UNDECIDABLE = "undecidable"

# The sample rules this job knows how to enforce. Anything else is refused
# rather than guessed at, because guessing means declaring a winner early.
RULE_PER_CAMPAIGN = "per arm, per campaign"
RULE_POOLED = "per arm, pooled"
RULE_POOLED_NICHE = "per arm, pooled across campaigns of one niche"


class ExperimentLogError(Exception):
    pass


# --------------------------------------------------------------------- seed
def _result_blank() -> Dict[str, Any]:
    return {"winner": None, "loser": None, "p_value": None, "reason": None, "decided_at": None}


def seed_document(as_of: str = "2026-09-22") -> Dict[str, Any]:
    """The tests M4 names, seeded against the Phase 0 change-set as staged.

    Test 1 is already built: ``changesets/instantly_phase0/sequences/*.json``
    stages a variant B on step 1 of all six campaigns. It used to be recorded
    as one test, "the call ask against the list ask, everything else the
    same", pooled over all six campaigns. That was wrong on two counts
    (MKT-8, owner decision R12, 2026-09-22):

    * Every B rewrites the whole email, not just the ask: a niche-specific
      opening line, the mechanism restated for ``{{companyName}}``, a shorter
      no-risk line, and a new ask.
    * The ask is not the same change everywhere. In the three reactivation
      campaigns B asks the prospect to send a list ("send me your list of lost
      bids or former clients / former clients or inquiries that never signed /
      dormant client accounts and I'll show you which ones are worth
      chasing"). In the three trigger and outbound campaigns B offers to send
      the prospect a list ("Want me to send over the trigger list I'd start
      with? ... Reply yes and I'll get it over").

    So test 1 is two tests, EXP-001a (reactivation) and EXP-001b (trigger),
    each described as the whole-email rewrite it is, and each starts the day
    that change-set is applied.

    Test 2 is not built: it needs the list factory (A6) to stamp each lead
    with the icebreaker style it was written in, which nothing does yet.
    """
    reactivation = ["cleaning_reactivation", "bookkeeping_reactivation", "recruiting_reactivation"]
    trigger = ["cleaning_trigger", "bookkeeping_trigger", "recruiting_outbound"]
    all_campaigns = [
        "cleaning_reactivation", "cleaning_trigger",
        "bookkeeping_reactivation", "bookkeeping_trigger",
        "recruiting_reactivation", "recruiting_outbound",
    ]
    split_note = ("split from EXP-001-cta-friction on 2026-09-22 (owner decision R12): the old record "
                  "pooled six campaigns whose B variants make two different changes")
    start_note = "starts when changesets/instantly_phase0 is applied; no B variant is live yet"
    return {
        "_about": (
            "Every running copy experiment (Blueprint M4). jobs/campaign_verdicts.py refreshes "
            "current_sample, observed and result on every run; the hypothesis, arms and "
            "sample_needed are written by hand. Nothing here touches a live system."
        ),
        "as_of": as_of,
        "updated_at": None,
        "rules": {
            "variant_min_sends": V.VARIANT_MIN_SENDS,
            "alpha": TH.EXPERIMENT_ALPHA,
            "note": (
                "A variant is judged at 500 sends or more per variant (M3.3). The p-value is a "
                "tie-breaker on top of that rule, never a licence to judge a smaller sample. A "
                "campaign that is paused, sends nothing or sits at its M4 retirement line is left "
                "out of the decision with the reason recorded; if every campaign is left out the "
                "test is undecidable."
            ),
        },
        "experiments": [
            {
                "id": "EXP-001a-reactivation-rewrite",
                "name": "Reactivation step 1: the live email against a rewrite that asks for the list",
                "campaigns": list(reactivation),
                "hypothesis": (
                    "Asking the prospect to send their lost-bid, former-client or dormant-account "
                    "list is a smaller ask than a call, so it gets more replies, and the replies "
                    "self-qualify because only someone with a list can answer."
                ),
                "what_changed": (
                    "Step 1 variant B is a rewrite of the whole email, not a one-line swap. It "
                    "opens on a niche-specific line ('I build reactivation systems for commercial "
                    "cleaning companies / bookkeeping and tax firms / recruiting agencies'), "
                    "restates the mechanism for {{companyName}}, shortens the no-risk line, and "
                    "ends on 'send me your list of lost bids or former clients' (cleaning), 'former "
                    "clients or inquiries that never signed' (bookkeeping) or 'dormant client "
                    "accounts' (recruiting) 'and I'll show you which ones are worth chasing'. "
                    "Variant A is the copy live today: a 15-minute call ask in bookkeeping and "
                    "recruiting, and in cleaning a commission-only 'would you be open to it? Let "
                    "me know' ask with a different opening. A result credits the whole rewrite, "
                    "not the ask alone."
                ),
                "start_date": None,
                "start_note": start_note,
                "split_note": split_note,
                "sample_needed": V.VARIANT_MIN_SENDS,
                "sample_rule": RULE_PER_CAMPAIGN,
                "metric": "positives",
                "arms": [
                    {"label": "A", "description": "the step-1 email live today (control)"},
                    {"label": "B", "description": "whole-email rewrite ending on the send-me-your-list ask"},
                ],
                "measure": {"kind": "campaign_variant", "step": 1, "arms": {"A": 0, "B": 1}},
                "current_sample": {},
                "observed": {},
                "status": STATUS_PLANNED,
                "result": _result_blank(),
            },
            {
                "id": "EXP-001b-trigger-rewrite",
                "name": "Trigger step 1: the live call ask against a rewrite that offers the trigger list",
                "campaigns": list(trigger),
                "hypothesis": (
                    "Offering to send the prospect the trigger list (the leases, filings or stuck "
                    "roles the system would work from) is a smaller ask than a call, so more "
                    "owners reply yes, and a yes is a warm opening for the call."
                ),
                "what_changed": (
                    "Step 1 variant B is a rewrite of the whole email, not a one-line swap. It "
                    "opens on a niche-specific line, restates the trigger mechanism for "
                    "{{companyName}} (cleaning: 'I watch {{metro}} for new leases ... at "
                    "{{buildingType}}', so it needs those two lead variables; recruiting: roles "
                    "open more than three weeks), adds a one-line benefit, rewords the guarantee "
                    "as a condition, and ends on an offer to send the prospect a list ('Want me to "
                    "send over the trigger list I'd start with? ... Reply yes and I'll get it "
                    "over'). Variant A is the copy live today, ending on a 15-minute call ask. "
                    "This is not the send-me-your-list ask EXP-001a tests: here the list goes to "
                    "the prospect. A result credits the whole rewrite, not the ask alone."
                ),
                "start_date": None,
                "start_note": start_note,
                "split_note": split_note,
                "sample_needed": V.VARIANT_MIN_SENDS,
                "sample_rule": RULE_PER_CAMPAIGN,
                "metric": "positives",
                "arms": [
                    {"label": "A", "description": "the step-1 email live today, 15-minute call ask (control)"},
                    {"label": "B", "description": "whole-email rewrite ending on an offer to send the trigger list"},
                ],
                "measure": {"kind": "campaign_variant", "step": 1, "arms": {"A": 0, "B": 1}},
                "current_sample": {},
                "observed": {},
                "status": STATUS_PLANNED,
                "result": _result_blank(),
            },
            {
                "id": "EXP-002-icebreaker-style",
                "name": "Compliment icebreaker against 10-minute research against none",
                "campaigns": list(all_campaigns),
                "hypothesis": (
                    "A first line built from ten minutes of research (service area, building "
                    "types, a lost-bid hypothesis) beats a compliment, and a compliment barely "
                    "beats no icebreaker at all, because the compliment is the part every other "
                    "cold email also has."
                ),
                "what_changed": (
                    "The {{personalization}} line only. Arm 1 is the compliment line the leads "
                    "carry today. Arm 2 is a researched line naming the service area, the "
                    "building types and a lost-bid hypothesis. Arm 3 opens on the offer sentence "
                    "with no first line at all. M4: test a whole sentence, not a word."
                ),
                "start_date": None,
                "sample_needed": V.VARIANT_MIN_SENDS,
                "sample_rule": RULE_POOLED_NICHE,
                "metric": "positives",
                "arms": [
                    {"label": "compliment", "description": "the line the live leads carry"},
                    {"label": "researched", "description": "service area, building types, lost-bid hypothesis"},
                    {"label": "none", "description": "no first line, straight into the offer sentence"},
                ],
                "measure": {
                    "kind": "lead_variable",
                    "variable": "icebreaker_style",
                    "values": {"compliment": "compliment", "researched": "researched", "none": "none"},
                },
                "current_sample": {},
                "observed": {},
                "status": STATUS_BLOCKED,
                "blocked_reason": (
                    "No lead carries an icebreaker_style variable, so the arms cannot be told "
                    "apart. The list factory (A6) has to stamp it at personalization time and "
                    "Instantly has to carry it as a custom variable before this test can be "
                    "counted."
                ),
                "result": _result_blank(),
            },
        ],
    }


# --------------------------------------------------------------------- i/o
def load(path: Optional[str] = None, seed_if_missing: bool = True) -> Dict[str, Any]:
    path = path or DEFAULT_PATH
    if not os.path.exists(path):
        if not seed_if_missing:
            raise ExperimentLogError("experiments file not found: %s" % path)
        logger.info("%s does not exist; seeding it", path)
        return seed_document()
    with open(path, "r", encoding="utf-8") as fh:
        try:
            doc = json.load(fh)
        except ValueError as exc:
            # Never silently start from an empty log: that would restart every
            # running test at zero sample and re-decide it on the next run.
            raise ExperimentLogError("%s is not valid JSON (%s). Fix or delete it; do not let a "
                                     "run start from an empty experiment log." % (path, exc))
    if not isinstance(doc, dict) or not isinstance(doc.get("experiments"), list):
        raise ExperimentLogError("%s has no experiments list" % path)
    return doc


def save(doc: Dict[str, Any], path: Optional[str] = None) -> str:
    path = path or DEFAULT_PATH
    directory = os.path.dirname(path)
    if directory and not os.path.isdir(directory):
        os.makedirs(directory)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, sort_keys=False)
        fh.write("\n")
    os.replace(tmp, path)
    return path


# ------------------------------------------------------------------ update
_EMPTY_ARM = {"sends": 0, "real_replies": 0, "positives": 0}
_FIELDS = ("sends", "real_replies", "positives")


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def campaign_variant_cells(
    experiment: Dict[str, Any], stats_by_key: Dict[str, Any]
) -> Dict[str, Dict[str, Dict[str, int]]]:
    """``{campaign_key: {arm: {sends, real_replies, positives}}}`` for the
    step this experiment tests.

    Per campaign, deliberately. Pooling happens later and only where the
    experiment's ``sample_rule`` says it may.
    """
    measure = experiment.get("measure") or {}
    step = _as_int(measure.get("step"), 1)
    arms = measure.get("arms") or {}
    cells = {}  # type: Dict[str, Dict[str, Dict[str, int]]]
    for key in experiment.get("campaigns") or []:
        stats = stats_by_key.get(key)
        if stats is None:
            continue
        by_variant = {c.variant: c for c in stats.variants_for_step(step)}
        row = {}
        for label, index in arms.items():
            cell = by_variant.get(_as_int(index))
            row[label] = {
                "sends": cell.sent if cell is not None else 0,
                "real_replies": cell.replies if cell is not None else 0,
                "positives": cell.positives if cell is not None else 0,
            }
        cells[key] = row
    return cells


def pool(cells: Dict[str, Dict[str, Dict[str, int]]], keys: Optional[List[str]] = None) -> Dict[str, Any]:
    """Sum the per-campaign cells into per-arm counters."""
    arms = set()
    for row in cells.values():
        arms |= set(row.keys())
    observed = {arm: dict(_EMPTY_ARM) for arm in arms}
    for key, row in cells.items():
        if keys is not None and key not in keys:
            continue
        for arm, values in row.items():
            for field in _FIELDS:
                observed[arm][field] += values.get(field, 0)
    return observed


def sample_gate(
    experiment: Dict[str, Any],
    cells: Dict[str, Dict[str, Dict[str, int]]],
    stats_by_key: Dict[str, Any],
) -> Dict[str, Any]:
    """Whether this experiment has the sample its own ``sample_rule`` demands.

    ``scope`` is the campaigns that are actually running every arm; only those
    are compared, so the pooled numbers never put campaign X's control against
    campaign Y's treatment.
    """
    rule_text = experiment.get("sample_rule") or RULE_PER_CAMPAIGN
    rule = rule_text.strip().lower()
    needed = _as_int(experiment.get("sample_needed"), V.VARIANT_MIN_SENDS) or V.VARIANT_MIN_SENDS
    excluded = {}  # type: Dict[str, str]
    for key in cells:
        reason = exclusion_reason(stats_by_key.get(key))
        if reason:
            excluded[key] = reason
    scope = sorted([k for k, row in cells.items()
                    if k not in excluded and row and all(v["sends"] > 0 for v in row.values())])
    gate = {
        "rule": rule_text,
        "needed_per_arm": needed,
        "scope": scope,
        "excluded": excluded,
        "met": False,
        "unknown_rule": False,
        "undecidable": None,
        "shortfall": [],
    }  # type: Dict[str, Any]
    if cells and len(excluded) == len(cells):
        gate["undecidable"] = (
            "every campaign carrying this test is out of it: %s. No sample can arrive, so the test "
            "cannot be decided; drop it or move it to campaigns that are sending"
            % "; ".join("%s (%s)" % (k, excluded[k]) for k in sorted(excluded)))
        gate["shortfall"] = [gate["undecidable"]]
        return gate
    if not scope:
        gate["shortfall"] = ["no campaign is running every arm yet"]
        return gate

    if "per campaign" in rule:
        short = []
        for key in scope:
            for arm in sorted(cells[key]):
                have = cells[key][arm]["sends"]
                if have < needed:
                    line = "%s %s has %d of %d sends" % (key, arm, have, needed)
                    stats = stats_by_key.get(key)
                    if (stats is not None and getattr(stats, "niche", "") in V.RETIRE_IF_ZERO_NICHES
                            and not getattr(stats, "positives", 0)):
                        line += (" (M4 retires it at %d sends if it still has zero positives, which "
                                 "takes it out of this test)" % V.VERDICT_LINE)
                    short.append(line)
        gate["shortfall"] = short
        gate["met"] = not short
        gate["description"] = "%d sends per arm in each of %d campaign(s)" % (needed, len(scope))
    elif "niche" in rule:
        groups = {}  # type: Dict[str, List[str]]
        for key in scope:
            niche = getattr(stats_by_key.get(key), "niche", "") or "unknown"
            groups.setdefault(niche, []).append(key)
        short = []
        for niche in sorted(groups):
            pooled = pool(cells, groups[niche])
            for arm in sorted(pooled):
                if pooled[arm]["sends"] < needed:
                    short.append("%s %s has %d of %d sends pooled across the niche"
                                 % (niche, arm, pooled[arm]["sends"], needed))
        gate["shortfall"] = short
        gate["met"] = not short
        gate["groups"] = {n: groups[n] for n in groups}
        gate["description"] = "%d sends per arm pooled inside each of %d niche(s)" % (needed, len(groups))
    elif "pooled" in rule:
        # Pooling across campaigns of different niches buys nothing but noise,
        # so a cross-campaign pool still needs the per-campaign sample in
        # total: 500 x the campaigns carrying the test.
        pooled = pool(cells, scope)
        needed_total = needed * len(scope)
        short = ["%s has %d of %d sends pooled" % (arm, pooled[arm]["sends"], needed_total)
                 for arm in sorted(pooled) if pooled[arm]["sends"] < needed_total]
        gate["shortfall"] = short
        gate["met"] = not short
        gate["needed_pooled"] = needed_total
        gate["description"] = "%d sends per arm pooled across %d campaign(s)" % (needed_total, len(scope))
    else:
        gate["unknown_rule"] = True
        gate["shortfall"] = [
            "sample_rule %r is not one of %r, %r or %r, so this job will not decide the test"
            % (rule_text, RULE_PER_CAMPAIGN, RULE_POOLED, RULE_POOLED_NICHE)]
    return gate


def exclusion_reason(stats: Any) -> Optional[str]:
    """Why a campaign cannot keep gathering sample for a test, or None.

    Owner decision R12: a campaign that is paused or retired, that sends
    nothing, or that ``verdicts.decide`` puts at ``retire`` is left out of the
    decision rather than holding the test open for ever.
    """
    if stats is None:
        return None
    if not getattr(stats, "is_active", True):
        return "campaign is not active (status %s): paused or retired" % getattr(stats, "status", None)
    if getattr(stats, "sends_nothing", False):
        return "sent nothing in the pulled window"
    try:
        verdict = V.decide(stats)
    except Exception:  # noqa: BLE001 - a verdict fault must not decide a test
        logger.exception("could not compute the verdict for %s", getattr(stats, "key", "?"))
        return None
    if verdict.recommendation == "retire":
        return "at its M4 retirement line (%d sends, %d positives)" % (stats.sent, stats.positives)
    return None


def _decide(experiment: Dict[str, Any], observed: Dict[str, Any], as_of: str,
            gate: Dict[str, Any]) -> Dict[str, Any]:
    """Winner / loser once the sample rule is satisfied."""
    metric = experiment.get("metric") or "positives"
    result = {"winner": None, "loser": None, "p_value": None, "reason": None, "decided_at": None}
    arms = sorted(observed.keys())
    if len(arms) < 2:
        result["reason"] = "fewer than two arms carry data"
        return result
    if not gate.get("met"):
        prefix = "sample rule %r not met" % gate.get("rule")
        result["reason"] = "%s: %s" % (prefix, "; ".join(gate.get("shortfall") or ["unknown"]))
        return result
    ranked = sorted(
        arms,
        key=lambda a: (float(observed[a].get(metric, 0)) / float(observed[a]["sends"] or 1),
                       observed[a].get(metric, 0)),
        reverse=True,
    )
    best, worst = ranked[0], ranked[-1]
    p = V.two_proportion_p(
        observed[best].get(metric, 0), observed[best]["sends"],
        observed[worst].get(metric, 0), observed[worst]["sends"],
    )
    result["p_value"] = round(p, 4) if p is not None else None
    if p is None:
        result["reason"] = "no %s on any arm yet; both arms are at sample but there is nothing to " \
                           "separate" % metric
        return result
    if p < TH.EXPERIMENT_ALPHA:
        result["winner"] = best
        result["loser"] = worst
        result["decided_at"] = as_of
        result["reason"] = "%s %d %s in %d sends beats %s %d in %d, p=%.3f" % (
            best, observed[best].get(metric, 0), metric, observed[best]["sends"],
            worst, observed[worst].get(metric, 0), observed[worst]["sends"], p)
    else:
        result["reason"] = "%s leads %s on %s but p=%.3f, so the arms are not separable yet" % (
            best, worst, metric, p)
    return result


def is_decided(experiment: Dict[str, Any]) -> bool:
    """A test whose decision has been taken and must not be recomputed."""
    result = experiment.get("result") or {}
    return bool(experiment.get("status") == STATUS_DECIDED
                and result.get("winner")
                and result.get("decided_at"))


def _sample_jump_note(before: Dict[str, Any], after: Dict[str, Any], needed: int) -> Optional[str]:
    """A run that sees an arm go from nothing to a full sample has missed runs.

    The elapsed time of the test is then wrong by the length of the gap, and
    ``start_date`` (the first run that saw both arms) is later than the day the
    change-set actually went live.
    """
    jumped = [a for a in after
              if after[a] >= needed and _as_int(before.get(a), 0) == 0 and before]
    if not jumped:
        return None
    return ("arm(s) %s went from 0 to a full sample in one run, so a run was missed: start_date is "
            "the first run that saw both arms, not the day the change-set was applied"
            % ", ".join(sorted(jumped)))


def update(doc: Dict[str, Any], stats_by_key: Dict[str, Any], as_of: str) -> List[Dict[str, Any]]:
    """Refresh every experiment in place. Returns one change record per
    experiment for the job's Job_Log row and the printed table."""
    changes = []
    for experiment in doc.get("experiments") or []:
        before_status = experiment.get("status")
        before_sample = dict(experiment.get("current_sample") or {})
        kind = (experiment.get("measure") or {}).get("kind")
        if kind == "campaign_variant":
            cells = campaign_variant_cells(experiment, stats_by_key)
            observed = pool(cells)
            gate = sample_gate(experiment, cells, stats_by_key)
            experiment["observed"] = observed
            experiment["observed_by_campaign"] = cells
            experiment["current_sample"] = {a: observed[a]["sends"] for a in observed}
            experiment["current_sample_by_campaign"] = {
                key: {arm: cells[key][arm]["sends"] for arm in cells[key]} for key in cells
            }
            experiment["sample_gate"] = gate
            live_arms = [a for a in observed if observed[a]["sends"] > 0]
            scoped = pool(cells, gate["scope"])
            if is_decided(experiment):
                # Frozen. Keep refreshing the numbers; never touch the result.
                experiment["post_decision"] = {
                    "as_of": as_of,
                    "observed": scoped,
                    "recomputed": _decide(experiment, scoped, as_of, gate),
                    "note": "the decision above is frozen; clear result.decided_at by hand to "
                            "re-open this test",
                }
            elif gate.get("undecidable"):
                experiment["status"] = STATUS_UNDECIDABLE
                experiment["result"] = {
                    "winner": None, "loser": None, "p_value": None, "decided_at": None,
                    "reason": gate["undecidable"],
                }
            elif len(live_arms) < 2:
                experiment["status"] = STATUS_PLANNED
                experiment["result"] = {
                    "winner": None, "loser": None, "p_value": None, "decided_at": None,
                    "reason": "only %d of %d arms %s sent anything; the change-set that stages the "
                              "other arm has not been applied"
                              % (len(live_arms), len(observed), "has" if len(live_arms) == 1 else "have"),
                }
            else:
                if not experiment.get("start_date"):
                    experiment["start_date"] = as_of
                    experiment["start_date_source"] = "first run that saw every arm sending"
                    jump = _sample_jump_note(before_sample, experiment["current_sample"],
                                             gate["needed_per_arm"])
                    if jump:
                        experiment["start_date_warning"] = jump
                result = _decide(experiment, scoped, as_of, gate)
                experiment["result"] = result
                experiment["status"] = STATUS_DECIDED if result["winner"] else STATUS_RUNNING
        elif kind == "lead_variable":
            experiment["status"] = STATUS_BLOCKED
            experiment["current_sample"] = {}
            experiment["observed"] = {}
        else:
            experiment["status"] = STATUS_BLOCKED
            experiment["blocked_reason"] = "unknown measure kind %r" % kind
        gate = experiment.get("sample_gate") or {}
        changes.append({
            "id": experiment.get("id"),
            "status_before": before_status,
            "status": experiment.get("status"),
            "sample_before": before_sample,
            "sample": dict(experiment.get("current_sample") or {}),
            "sample_by_campaign": dict(experiment.get("current_sample_by_campaign") or {}),
            "sample_rule": gate.get("rule"),
            "sample_met": gate.get("met"),
            "excluded": dict(gate.get("excluded") or {}),
            "frozen": bool(experiment.get("post_decision")) and is_decided(experiment),
            "winner": (experiment.get("result") or {}).get("winner"),
            "reason": (experiment.get("result") or {}).get("reason") or experiment.get("blocked_reason"),
        })
    doc["updated_at"] = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()
    doc["as_of"] = as_of
    return changes
