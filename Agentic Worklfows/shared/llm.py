"""Claude access with a role -> model policy, fake mode for tests, a cost
ledger and a hard spend ceiling.

    from shared.llm import complete
    label = complete("classify", system, user, json_mode=True)   # dict
    body  = complete("draft", system, user)                      # str

LLM_FAKE=1 returns canned responses (register_fake(role, fn) to override) and
never imports the anthropic client. Every call, real or fake, appends a row to
.tmp/llm_ledger.csv.

Every BILLED call is also checked against a cumulative USD ceiling first
(``config/llm_budget.json``, default $10.00). Over the cap, ``complete``
raises ``LLMBudgetExceeded`` instead of calling the model, and Lorenzo gets one
push. See "the spend ceiling" below for why the number is what it is.
"""
import csv
import json
import logging
import os
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional, Union

from shared.paths import CONFIG_DIR, tmp_file

logger = logging.getLogger("shared.llm")

# Every role runs on Claude Opus 5.5 (Lorenzo, 2026-09-25): classification,
# escalation, drafts, research lines, retro and proposals. The role keys stay
# because callers name them; this dict is the single place to change a model.
OPUS_5_5 = "claude-opus-5-5"
MODEL_POLICY = {
    "classify": OPUS_5_5,
    "draft": OPUS_5_5,
    "research": OPUS_5_5,
    "retro": OPUS_5_5,
    "proposal": OPUS_5_5,
    "escalate": OPUS_5_5,
}

# Thinking control per role, sent on every real call.
#
# HISTORY: until 2026-09-25 every call sent ``thinking={"type": "disabled"}``.
# claude-sonnet-5 thinks adaptively when a request carries no ``thinking``
# parameter; on a real Upwork drafting prompt (shadow test, 2026-09-23) it
# spent about 480 output tokens thinking before a ~380-char text block, so the
# max_tokens=400 cap stopped the call and complete() raised "cut off at
# max_tokens".
#
# ON claude-opus-5-5 THINKING CANNOT BE DISABLED. Per the claude-api skill
# (shared/model-migration.md, "Migrating to Claude Opus 5.5", breaking change
# 1): ``{"type": "disabled"}`` and ``{"type": "enabled", "budget_tokens": N}``
# both return a 400 at every effort level. Thinking is always on (omitting
# ``thinking`` runs adaptive), and ``output_config.effort`` is the only control
# for how much it thinks. The default effort on Opus 5.5 is ``medium``, so it
# is always sent explicitly. So now:
#   1. ``thinking`` is never sent (sending any shape but adaptive is a 400);
#   2. every call sends ``output_config={"effort": EFFORT_POLICY[role]}``,
#      ``low`` for every role, which keeps thinking short (the skill's advice
#      for a route that used to run with thinking disabled);
#   3. thinking counts toward ``max_tokens``, so the API request gets
#      ``reserved_output_tokens(max_tokens)`` = ``max_tokens +
#      THINKING_HEADROOM_TOKENS``. Without the headroom a 120-token
#      classification cap would be eaten by a short thinking block and the
#      max_tokens guard in complete() would refuse the reply. The API's limit
#      is that padded number across thinking AND text together, so the
#      caller's ``max_tokens`` is NOT a hard cap on the reply any more: a call
#      that thinks little can write up to THINKING_HEADROOM_TOKENS more text
#      than the caller asked for. Text that auto-sends keeps its own length
#      checks (reply_engine/draft.py validate_draft, 1,500 chars;
#      reply_engine/proposal.py copy_problems, MAX_PROPOSAL_CHARS). The spend
#      ceiling reserves against the padded number, and a caller that keeps
#      its own per-run budget (upwork_followup/tick.py call_cost) prices the
#      same padded number through reserved_cost_usd().
# Raising a role's effort (``medium``/``high``/``xhigh``/``max``) means more
# thinking tokens on every call for that role; raise THINKING_HEADROOM_TOKENS
# with it. Any value outside VALID_EFFORTS raises LLMError before the call
# bills. A role missing here gets ``low``.
VALID_EFFORTS = ("low", "medium", "high", "xhigh", "max")
DEFAULT_EFFORT = "low"
EFFORT_POLICY = {
    "classify": DEFAULT_EFFORT,
    "draft": DEFAULT_EFFORT,
    "research": DEFAULT_EFFORT,
    "retro": DEFAULT_EFFORT,
    "proposal": DEFAULT_EFFORT,
    "escalate": DEFAULT_EFFORT,
}
THINKING_HEADROOM_TOKENS = 1024

# Undated aliases the API also accepts for a model that IS in MODEL_POLICY.
# An alias is priced identically to its target; test_llm pins that, so an
# alias can never drift into a second, wrong price for the same model.
MODEL_ALIASES = {}  # type: Dict[str, str]

# USD per 1M tokens (input, output). Anthropic first-party list prices; Opus
# 5.5 is $4 / $20 per the claude-api skill's model table (2026-09-25). UPDATE THIS DICT when
# prices or model ids change; est_cost_usd in the ledger is derived from it.
#
# This table is CLOSED: exactly the models in MODEL_POLICY plus the aliases
# above, pinned by
# test_llm.py::test_every_priced_model_has_a_policy_role_and_the_reverse.
# A price with no role is a model nobody calls, and it reads like a model
# somebody still calls. ``claude-fable-5`` sat here until 2026-09-22, eleven
# months after Fable was retired and a day after Lorenzo's weekly Fable
# allowance ran out and every Fable role moved to Opus 5 (CLAUDE.md, "Runtime
# models"). Haiku 4.5, Sonnet 5 and Opus 5 left on 2026-09-25 when every role
# moved to Opus 5.5. Old ledger rows naming them, billed ones included (the
# main folder's .tmp/llm_ledger.csv holds 278 billed Haiku rows and 253 billed
# Sonnet rows), are unaffected: every reader (ledger_spend_usd, the cost
# audits) sums the est_cost_usd stored on the row when it was written and
# never re-prices a row by its model id. Only a NEW call is priced from this
# table, and a model id missing from it falls to DEFAULT_PRICE, which
# OVER-states the cost, so the spend ceiling below trips early rather than
# late.
PRICES_USD_PER_MTOK = {
    "claude-opus-5-5": (4.00, 20.00),
}
DEFAULT_PRICE = (10.00, 50.00)  # conservative fallback for unknown ids

# ``faked`` is 1 for an LLM_FAKE call. The row is still written with its
# est_cost_usd, because that number is the projection an offline rehearsal
# exists to produce ("a real run would cost this"), but a cost AUDIT that sums
# the column without reading this flag reports money that was never spent.
LEDGER_HEADER = ["ts", "role", "model", "input_tokens", "output_tokens", "est_cost_usd", "faked"]

FakeFn = Callable[[str, str, bool], Union[str, Dict[str, Any]]]
_FAKES = {}  # type: Dict[str, FakeFn]
_CLIENT = {"client": None, "warned": False}  # type: Dict[str, Any]


class LLMError(Exception):
    pass


TRUTHY = ("1", "true", "yes", "on", "y", "t")


def is_fake() -> bool:
    """LLM_FAKE accepts every ordinary spelling of true. Comparing to the exact
    string "1" meant a run started with LLM_FAKE=true billed every call."""
    return os.environ.get("LLM_FAKE", "").strip().lower() in TRUTHY


def model_for(role: str) -> str:
    return MODEL_POLICY.get(role, MODEL_POLICY["draft"])


def _effort_param(role: str) -> Dict[str, Any]:
    """The ``output_config`` kwarg for ``role`` from EFFORT_POLICY, validated.

    Raises LLMError on any value outside VALID_EFFORTS. Runs before the budget
    reservation, so a bad config costs nothing."""
    effort = EFFORT_POLICY.get(role, DEFAULT_EFFORT)
    if not isinstance(effort, str) or effort not in VALID_EFFORTS:
        raise LLMError("invalid EFFORT_POLICY for role=%s: %r" % (role, effort))
    return {"effort": effort}


def register_fake(role: str, fn: FakeFn) -> None:
    """fn(system, user, json_mode) -> str | dict, used when LLM_FAKE=1."""
    _FAKES[role] = fn


def clear_fakes() -> None:
    _FAKES.clear()


def fake_for(role: str) -> Optional[FakeFn]:
    """The fake registered for ``role``, or None when the built-in default applies.
    Callers that install their own offline stand-ins (services.reply_engine.classify)
    use this to tell 'nothing registered' from 'a test registered something else'."""
    return _FAKES.get(role)


def ledger_path():
    override = os.environ.get("LLM_LEDGER_PATH")
    return tmp_file("llm_ledger.csv") if not override else __import__("pathlib").Path(override)


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    price_in, price_out = PRICES_USD_PER_MTOK.get(model, DEFAULT_PRICE)
    return round((input_tokens * price_in + output_tokens * price_out) / 1_000_000.0, 6)


def migrate_ledger_header(path) -> bool:
    """Bring an older, narrower ledger up to ``LEDGER_HEADER``, in place.

    ``faked`` was appended to LEDGER_HEADER on 2026-09-22, but _record only
    ever wrote a header for a brand-new file, so the ledger already on disk
    kept its 6-column header over 1,020 six-field rows. csv.DictReader then
    returns no ``faked`` key for those rows, and ``ledger_spend_usd`` treats a
    missing flag as "billed": it reported $1.47957 of spend that never
    happened, and the documented audit ("filter on the flag rather than sum the
    column") could not be performed on the file that existed.

    Rows written before the flag existed were all produced under LLM_FAKE=1, so
    they backfill to ``faked=1``. Returns True when it rewrote the file.
    """
    try:
        with open(str(path), newline="", encoding="utf-8") as fh:
            rows = list(csv.reader(fh))
    except (IOError, OSError):
        return False
    if not rows:
        return False
    header = rows[0]
    if len(header) >= len(LEDGER_HEADER):
        return False

    missing = LEDGER_HEADER[len(header):]
    # "faked" is the only column that has ever been appended; a row that
    # predates it was written when every call was faked.
    defaults = ["1" if name == "faked" else "" for name in missing]
    width = len(LEDGER_HEADER)
    out = [list(LEDGER_HEADER)]
    for row in rows[1:]:
        if not row:
            continue
        if len(row) < width:
            row = list(row) + defaults[len(row) - len(header):]
        out.append(row[:width])
    tmp = str(path) + ".migrating"
    try:
        with open(tmp, "w", newline="", encoding="utf-8") as fh:
            csv.writer(fh).writerows(out)
        os.replace(tmp, str(path))
    except (IOError, OSError) as exc:
        logger.warning("llm ledger header migration failed: %s", exc)
        return False
    logger.info("llm ledger migrated to %d columns (%d rows backfilled)", width, len(out) - 1)
    return True


def _record(role: str, model: str, input_tokens: int, output_tokens: int) -> None:
    """Append one ledger row. The ledger is best-effort bookkeeping only: the
    spend ceiling is charged by complete() itself (a reservation before the
    call, reconciled after it), so a ledger write that fails cannot lose spend
    and a billed call is never counted twice."""
    faked = is_fake()
    path = ledger_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        new_file = not path.exists() or path.stat().st_size == 0
        if not new_file:
            migrate_ledger_header(path)
        with open(path, "a", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            if new_file:
                writer.writerow(LEDGER_HEADER)
            writer.writerow([
                datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                role,
                model,
                int(input_tokens),
                int(output_tokens),
                "%.6f" % estimate_cost(model, input_tokens, output_tokens),
                "1" if faked else "0",
            ])
    except Exception as exc:  # noqa: BLE001
        logger.warning("llm ledger write failed: %s", exc)


def _approx_tokens(text: str) -> int:
    return max(1, len(text or "") // 4)


# ---------------------------------------------------------- the spend ceiling
#
# WHY THIS EXISTS
# ---------------
# runbooks/GO_LIVE_CHECKLIST.md Stage 3 tells Lorenzo to deploy to Modal and
# watch it for 48 hours (3.1 is the spend check during that watch). That watch is MODE=shadow, so nothing WRITES, but LLM_FAKE
# is deliberately unset (modal_app.ENV_NOT_IN_SECRET: "a deployed container
# must never fake the model"), so every scheduled tick bills real tokens for
# two days against a number nobody had sized. Shadow bounds the damage a write
# can do; until this ceiling existed, nothing bounded the damage a LOOP could
# do to the bill.
#
# THE ARITHMETIC BEHIND THE DEFAULT (all figures from PRICES_USD_PER_MTOK)
# -----------------------------------------------------------------------
# Per-call cost on claude-opus-5-5 ($4 / $20 per MTok, every role since
# 2026-09-25), input estimated from the prompts, output at the reply cap:
#   classify  2,000 in /   300 out = $0.014    (classify.py:457)
#   escalate  2,000 in /   300 out = $0.014    (classify.py:463)
#   draft     4,000 in /   500 out = $0.026    (draft.py:631)
#   research  1,500 in /   120 out = $0.0084   (cadence.py:980)
#   proposal  6,000 in / 1,600 out = $0.056    (proposal.py:603)
#   retro    15,000 in / 2,000 out = $0.10     (lessons.py:529)
# Thinking is always on for Opus 5.5 and every call may spend up to
# THINKING_HEADROOM_TOKENS (1,024) more output, at most $0.0205 per call.
#
# A HEALTHY 48 hours, at today's 12 active inboxes x 25/day = 300 sends/day and
# a 3% reply rate (about 9 replies/day, 18 in the window):
#   18 classify $0.25 + 5 escalations $0.07 + 5 drafts $0.13
#   + 20 cadence research lines $0.17 + 4 precall proposals $0.22
#   + one Friday retro packet $0.10
#   = about $0.95, and about $2.00 if all 53 calls use the full thinking
#   headroom. Call it $2 for a busy two days.
#
# A RUNAWAY, which is the case a ceiling is for. modal_app.SCHEDULES runs
# precall_tick and poller on "*/5 * * * *": 576 runs in 48 hours. If the
# "already proposed" guard ever stops holding, that is 576 x $0.056 = $32 of
# Opus for ONE call in the window, about $0.67/hour. A poller re-classifying
# 20 open replies every tick is 576 x 20 x $0.014 = $161.
#
# DEFAULT_BUDGET_USD = $10.00 sits between the two on purpose: roughly 5x a
# busy watch at worst-case thinking, so a healthy 48 hours never sees it, and it
# stops either runaway at $10 rather than $32 to $161. It is a REHEARSAL
# number. Raise it in config/llm_budget.json before the tiers go live, where
# real reply volume is the point.
#
# WHAT COUNTS
# -----------
# Only billed calls. An LLM_FAKE call costs nothing, so it neither consumes the
# budget nor is refused by it, and the whole test suite is unaffected.
# The running total lives in the shared store (shared.store), not in the
# ledger CSV: on Modal each tick is a fresh container with a fresh .tmp, so a
# file-based total would reset every five minutes and bound nothing. The store
# is the modal.Dict in a container and .tmp/store.json locally, so the total
# survives across ticks, which is what "the 48-hour watch cannot exceed it"
# requires. If the store is unreachable the cap degrades to this process plus
# whatever the local ledger shows, and says so in the log.
#
# HOW A CALL IS CHARGED (SAF-8, 2026-09-22)
# -----------------------------------------
# Before each attempt, its worst case (prompts as measured, output at
# max_tokens) is RESERVED: checked against the cap and added to the total in
# one locked step. A failed attempt keeps its reservation; a successful one is
# reconciled to the cost its usage block reports. Charging only after a
# successful response let a failing call cost nothing, let the SDK's own
# retries go uncounted, and let concurrent calls all pass the same check.
BUDGET_PATH = CONFIG_DIR / "llm_budget.json"
DEFAULT_BUDGET_USD = 10.00
DEFAULT_WARN_FRACTION = 0.80
SPEND_KEY = "llm.spend_usd"
# The counter period: a new id on every reset (reset_spend() here,
# changesets/deploy/budget.py reset on Modal). Each threshold alerts ONCE per
# period, claimed in the shared store under BUDGET_ALERT_PREFIX, so a fresh
# Modal container (a fresh process every scheduled run) does not push again.
SPEND_PERIOD_KEY = "llm.spend_period"
BUDGET_ALERT_PREFIX = "llm.budget_alert:"
INITIAL_PERIOD = "initial"

_SPEND = {"process": 0.0, "alerted": False, "warned": False}  # type: Dict[str, Any]

# Serialises check-and-reserve inside one process. Across processes the same
# step runs inside store.mutate(), which holds the store's own lock, so two
# containers cannot both see the last dollar free either.
_SPEND_LOCK = threading.RLock()


class LLMBudgetExceeded(LLMError):
    """The cumulative USD ceiling is reached; no further billed call is made.

    A subclass of LLMError on purpose: every caller already handles LLMError by
    degrading (classify -> unsure, draft -> no draft), so hitting the cap
    cannot crash a tick. The push and the Job_Log row are what make it loud.
    """


def budget_config() -> Dict[str, Any]:
    """{'budget_usd', 'warn_at_fraction'} from config/llm_budget.json.

    Never raises and never fails OPEN: a missing, malformed or nonsense file
    leaves the conservative default in place. In particular budget_usd <= 0 is
    NOT read as "unlimited" (a typo must not remove the ceiling) and not as
    "refuse everything" either; it falls back to the default with a warning.
    """
    cfg = {"budget_usd": DEFAULT_BUDGET_USD, "warn_at_fraction": DEFAULT_WARN_FRACTION}
    try:
        with open(str(BUDGET_PATH), "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except IOError:
        return cfg
    except Exception as exc:  # noqa: BLE001 - malformed JSON must not stop a tick
        logger.warning("llm budget config unreadable (%s); using the $%.2f default",
                       exc, DEFAULT_BUDGET_USD)
        return cfg
    if not isinstance(raw, dict):
        logger.warning("llm budget config is not an object; using the $%.2f default", DEFAULT_BUDGET_USD)
        return cfg
    if "budget_usd" in raw:
        try:
            value = float(raw["budget_usd"])
        except (TypeError, ValueError):
            logger.warning("llm budget_usd=%r is not a number; using $%.2f", raw["budget_usd"], DEFAULT_BUDGET_USD)
        else:
            if value > 0:
                cfg["budget_usd"] = value
            else:
                logger.warning(
                    "llm budget_usd=%r is not a positive number; 0 does not mean unlimited. "
                    "Using the $%.2f default.", raw["budget_usd"], DEFAULT_BUDGET_USD)
    if "warn_at_fraction" in raw:
        try:
            fraction = float(raw["warn_at_fraction"])
        except (TypeError, ValueError):
            fraction = -1.0
        if 0 < fraction <= 1:
            cfg["warn_at_fraction"] = fraction
        else:
            logger.warning("llm warn_at_fraction=%r is not in (0, 1]; using %.2f",
                           raw.get("warn_at_fraction"), DEFAULT_WARN_FRACTION)
    return cfg


def budget_usd() -> float:
    return float(budget_config()["budget_usd"])


def _store():
    from shared import store as store_mod  # local import: shared.store must not be a load-time dep

    return store_mod.get_store()


def ledger_spend_usd(path=None) -> float:
    """Billed spend according to the local ledger CSV. Faked rows are excluded:
    their est_cost_usd is a projection of what a real run WOULD cost, not money.
    Used only as the fallback when the shared store is unreachable."""
    path = path or ledger_path()
    total = 0.0
    try:
        with open(str(path), newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                if str(row.get("faked", "0")).strip() == "1":
                    continue
                try:
                    total += float(row.get("est_cost_usd") or 0.0)
                except (TypeError, ValueError):
                    continue
    except IOError:
        return 0.0
    except Exception as exc:  # noqa: BLE001
        logger.warning("llm ledger unreadable for the spend fallback: %s", exc)
        return 0.0
    return round(total, 6)


def spend_usd() -> float:
    """Cumulative BILLED spend since the last reset_spend(), across processes
    and (on Modal) across containers."""
    try:
        stored = _store().get(SPEND_KEY, 0.0)
        return round(max(float(stored or 0.0), _SPEND["process"]), 6)
    except Exception as exc:  # noqa: BLE001 - a store outage must not stop a tick
        logger.warning("llm spend counter unreadable (%s); falling back to this process and the ledger", exc)
        return round(max(_SPEND["process"], ledger_spend_usd()), 6)


def remaining_usd() -> float:
    return round(budget_usd() - spend_usd(), 6)


def budget_status() -> Dict[str, Any]:
    """One dict for the runbook one-liner and the morning check."""
    cap = budget_usd()
    spent = spend_usd()
    return {
        "budget_usd": round(cap, 6),
        "spent_usd": spent,
        "remaining_usd": round(cap - spent, 6),
        "over_budget": spent >= cap,
        "config_path": str(BUDGET_PATH),
    }


def new_period_id(now: Optional[datetime] = None) -> str:
    return (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%S%fZ")


def start_period(store, now: Optional[datetime] = None) -> str:
    """Zero ``store``'s counter and open a new counter period there, so each
    threshold can alert once more. Used by reset_spend() and by
    changesets/deploy/budget.py reset (the deployed Dict)."""
    period = new_period_id(now)
    store.set(SPEND_KEY, 0.0)
    store.set(SPEND_PERIOD_KEY, period)
    return period


def reset_spend() -> float:
    """Zero the running total (new watch, new billing period). Returns 0.0."""
    _SPEND["process"] = 0.0
    _SPEND["alerted"] = False
    _SPEND["warned"] = False
    try:
        start_period(_store())
    except Exception as exc:  # noqa: BLE001
        logger.warning("llm spend counter reset failed: %s", exc)
    return 0.0


def _add_spend(usd: float, to_store: bool = True) -> float:
    """Add ``usd`` (negative to refund part of a reservation) to the process
    counter and, unless ``to_store`` is False, to the shared store.

    A refund must go only where the reservation went. When the store was
    unreachable at reservation time the charge landed in this process alone;
    refunding the unused part from the store (recovered by then) took a $5.00
    total to $4.96 on a $0.00012 call.
    """
    with _SPEND_LOCK:
        _SPEND["process"] = round(max(0.0, _SPEND["process"] + float(usd)), 6)
        if not to_store:
            return _SPEND["process"]
        try:
            return float(_store().mutate(
                SPEND_KEY, lambda current: round(max(0.0, float(current or 0.0) + float(usd)), 6), default=0.0))
        except Exception as exc:  # noqa: BLE001
            logger.warning("llm spend counter write failed (%s): the ceiling now bounds this process only", exc)
            return _SPEND["process"]


def _try_reserve(cost: float, cap: float) -> Dict[str, Any]:
    """Atomically: if spend + ``cost`` fits under ``cap``, charge ``cost`` now
    and return {'ok': True, 'spent_usd': <spend before>, 'in_store': bool};
    otherwise charge nothing and return {'ok': False, 'spent_usd': <spend>}.
    ``in_store`` says whether the charge reached the shared store or only this
    process (store outage), so the reconcile can refund the same counter.

    The check and the charge are ONE step. Checking first and charging after
    the response came back (the pre-2026-09-22 shape) let every call already in
    flight pass the same check against the same total: concurrent calls took a
    $10.00 cap to $10.48, and a call that raised was never charged at all.
    """
    cost = float(cost)
    with _SPEND_LOCK:
        outcome = {}  # type: Dict[str, Any]

        def _reserve(current):
            stored = float(current or 0.0)
            spent = max(stored, _SPEND["process"])
            outcome["spent_usd"] = round(spent, 6)
            if spent + cost > cap:
                outcome["ok"] = False
                return stored
            outcome["ok"] = True
            return round(stored + cost, 6)

        try:
            _store().mutate(SPEND_KEY, _reserve, default=0.0)
            outcome["in_store"] = bool(outcome.get("ok"))
        except Exception as exc:  # noqa: BLE001 - a store outage must not stop a tick
            logger.warning("llm spend counter unreachable (%s); reserving against this process and the ledger",
                           exc)
            spent = round(max(_SPEND["process"], ledger_spend_usd()), 6)
            outcome = {"spent_usd": spent, "ok": spent + cost <= cap, "in_store": False}
        if outcome.get("ok"):
            _SPEND["process"] = round(_SPEND["process"] + cost, 6)
        return outcome


def projected_cost_usd(model: str, system: str, user: str, max_tokens: int) -> float:
    """Worst case for one call: the prompts as measured, the output at
    max_tokens. The check has to run BEFORE the call, so it assumes the model
    fills its budget. ``max_tokens`` here is the number SENT to the API; for a
    caller's reply cap use reserved_cost_usd(), which adds the thinking
    headroom the way complete() does."""
    return estimate_cost(model, _approx_tokens(system) + _approx_tokens(user), int(max_tokens))


def output_tokens_with_thinking(text_tokens: int, calls: int = 1) -> int:
    """``text_tokens`` of output plus the WORST-CASE thinking of ``calls``
    calls (THINKING_HEADROOM_TOKENS each). Thinking cannot be turned off on
    claude-opus-5-5 and bills as output, so a cost projection built from
    measured text-token averages needs this allowance to be a worst case.
    Nothing has measured the typical thinking length at effort ``low`` yet."""
    return int(text_tokens) + max(0, int(calls)) * THINKING_HEADROOM_TOKENS


def reserved_output_tokens(max_tokens: int) -> int:
    """The output tokens complete() asks the API for when a caller passes
    ``max_tokens``: the reply cap plus THINKING_HEADROOM_TOKENS. Thinking
    counts toward the limit, so this is also the worst-case output one call
    can bill, and the number any pre-call cost projection must price."""
    return output_tokens_with_thinking(max_tokens, 1)


def _request_system(system: str, json_mode: bool) -> str:
    """The system prompt complete() actually sends (and prices)."""
    if json_mode:
        return (system or "") + "\n\nRespond with a single JSON object and nothing else. No prose, no code fences."
    return system or ""


def reserved_cost_usd(role: str, system: str, user: str, max_tokens: int = 800,
                      json_mode: bool = False, model: Optional[str] = None) -> float:
    """What complete(role, system, user, max_tokens, json_mode, model) reserves
    against the spend ceiling on each attempt: the prompts as sent, the output
    at reserved_output_tokens(max_tokens). Callers that keep their own
    per-run budget (upwork_followup/tick.py call_cost) use this so their
    count cannot drift from the ceiling's."""
    model = model or model_for(role)
    return projected_cost_usd(model, _request_system(system, json_mode), user or "",
                              reserved_output_tokens(max_tokens))


def _alert_claim(threshold: str) -> bool:
    """True exactly once per threshold per counter period, across processes
    and containers (claimed in the shared store). The process latch is only
    the fallback when the store cannot be reached."""
    latch = "alerted" if threshold == "refused" else "warned"
    try:
        st = _store()
        period = st.get(SPEND_PERIOD_KEY) or INITIAL_PERIOD
        if _SPEND[latch] == period:
            return False
        won = bool(st.set_if_absent("%s%s:%s" % (BUDGET_ALERT_PREFIX, period, threshold),
                                    {"at": datetime.now(timezone.utc).isoformat(), "threshold": threshold}))
        _SPEND[latch] = period
        return won
    except Exception as exc:  # noqa: BLE001 - no store: alert once per process rather than never
        logger.warning("llm budget alert claim unavailable (%s); alerting once per process", exc)
        if _SPEND[latch]:
            return False
        _SPEND[latch] = True
        return True


def _on_modal() -> bool:
    return os.environ.get("RUNTIME") == "modal"


def budget_fix_text() -> str:
    """How to lift the stop, where this process runs. On Modal the counter is
    the deployed Dict and the cap is baked into the image."""
    if _on_modal():
        try:
            from shared import settings

            mode = "live" if settings.is_live() else "shadow"
        except Exception:  # noqa: BLE001
            mode = "shadow"
        return ("Reset the deployed counter from the laptop: python3 changesets/deploy/budget.py reset "
                "--store-mode %s (type RESET). Raising budget_usd in config/llm_budget.json needs a redeploy: the "
                "file is baked into the image (DEPLOY_TIERS=sales bash changesets/schedules/install_schedules.sh "
                "--deploy %s)." % (mode, mode))
    return ("Raise budget_usd in %s and reset the counter with\n"
            "python3 -c \"from shared import llm; llm.reset_spend()\"" % BUDGET_PATH)


def _notify_budget(title: str, message: str) -> None:
    try:
        from shared.notify import notify as _notify

        _notify(title, message, priority="high", tags=["money"])
    except Exception as exc:  # noqa: BLE001 - an alert that fails must not mask the refusal
        logger.warning("llm budget alert could not be sent: %s", exc)


def _log_budget(status: str, details: Dict[str, Any]) -> None:
    try:
        from shared import job_log

        job_log.log_run("llm.budget", status, details)
    except Exception as exc:  # noqa: BLE001
        logger.warning("llm budget Job_Log row failed: %s", exc)


def enforce_budget(role: str, model: str, system: str, user: str, max_tokens: int) -> Dict[str, Any]:
    """Reserve the worst-case cost of one billed call, or raise
    LLMBudgetExceeded rather than make a call that could carry cumulative spend
    past the ceiling. Alerts once per counter period (shared across processes
    and containers through the store) on the stop, and once on crossing
    warn_at_fraction.

    On success the projected cost is ALREADY charged ('reserved_usd' in the
    result; 'reserved_in_store' says whether the shared store got it). The
    caller keeps that charge if the call fails and reconciles it to the real
    cost with _add_spend(actual - reserved, to_store=reserved_in_store) if it
    succeeds.
    """
    cfg = budget_config()
    cap = float(cfg["budget_usd"])
    projected = projected_cost_usd(model, system, user, max_tokens)
    reservation = _try_reserve(projected, cap)
    spent = float(reservation["spent_usd"])
    if not reservation["ok"]:
        detail = {"role": role, "model": model, "spent_usd": spent, "projected_usd": projected,
                  "budget_usd": cap, "config_path": str(BUDGET_PATH)}
        if _alert_claim("refused"):
            _notify_budget(
                "LLM budget stop: $%.2f of $%.2f" % (spent, cap),
                "No further model call will be made. The next one (role=%s, model=%s) was projected at "
                "$%.4f. %s" % (role, model, projected, budget_fix_text()))
            _log_budget("refused", detail)
        raise LLMBudgetExceeded(
            "LLM spend ceiling reached: $%.4f spent of $%.2f, next call (role=%s, model=%s) projected at "
            "$%.4f. Nothing was sent to the model. %s" % (
                spent, cap, role, model, projected, budget_fix_text()))
    warn_at = cap * float(cfg["warn_at_fraction"])
    if spent >= warn_at and _alert_claim("warned"):
        _notify_budget(
            "LLM spend at $%.2f of $%.2f" % (spent, cap),
            "Model calls are still running. At the cap they stop. %s" % (
                "The cap is the one baked into the deployed image; raising it needs a redeploy "
                "(changesets/deploy/budget.py status shows the counter)." if _on_modal() else BUDGET_PATH))
        _log_budget("warned", {"spent_usd": spent, "budget_usd": cap, "warn_at_usd": round(warn_at, 6)})
    return {"budget_usd": cap, "spent_usd": spent, "projected_usd": projected, "reserved_usd": projected,
            "reserved_in_store": bool(reservation.get("in_store"))}


# ------------------------------------------------------------------ fakes
def _fake_classify(system: str, user: str, json_mode: bool) -> Dict[str, Any]:
    return {"label": "positive_interested", "confidence": 0.95, "reason": "fake"}


def _fake_draft(system: str, user: str, json_mode: bool) -> str:
    snippet = re.sub(r"\s+", " ", (user or "")).strip()[:120]
    return (
        "Hey there,\n\n"
        "Thanks for getting back to me. Quick answer to your note (%s).\n\n"
        "Would Tue 2:00 or Thu 3:30 CT work for a 15 minute call?\n\n"
        "Lorenzo" % snippet
    )


def _fake_generic(role: str) -> FakeFn:
    def fn(system: str, user: str, json_mode: bool):
        if json_mode:
            return {"role": role, "fake": True, "input": (user or "")[:200]}
        return "FAKE[%s]: %s" % (role, (user or "")[:200])

    return fn


def _fake_response(role: str, system: str, user: str, json_mode: bool) -> Union[str, Dict[str, Any]]:
    fn = _FAKES.get(role)
    if fn is None:
        if role == "classify":
            fn = _fake_classify
        elif role == "draft":
            fn = _fake_draft
        else:
            fn = _fake_generic(role)
    out = fn(system, user, json_mode)
    if json_mode and isinstance(out, str):
        out = _parse_json(out)
    return out


# ------------------------------------------------------------------- real
#
# RETRIES ARE OURS, NOT THE SDK'S
# -------------------------------
# anthropic.Anthropic() retries a failed request twice by default, invisibly,
# so one complete() could be three billed attempts against one budget check.
# The client is built with max_retries=0 and complete() retries itself: every
# attempt reserves its own worst case through enforce_budget() first, so the
# ceiling sees every request that leaves the process, and a retry the budget
# cannot afford is refused instead of sent.
MAX_ATTEMPTS = 3                 # the SDK default was 1 try + 2 retries
RETRY_BACKOFF_SECONDS = (1.0, 4.0)
_RETRYABLE_STATUS = (408, 409, 429, 500, 502, 503, 504, 529)
_RETRYABLE_NAMES = ("APIConnectionError", "APITimeoutError", "RateLimitError", "InternalServerError",
                    "OverloadedError", "ServiceUnavailableError")
_sleep = time.sleep  # test seam


def _client():
    if _CLIENT["client"] is None:
        import anthropic  # lazy: not needed in fake mode

        _CLIENT["client"] = anthropic.Anthropic(max_retries=0)
    return _CLIENT["client"]


def _is_retryable(exc: BaseException) -> bool:
    """Transient API failures only. Read by name and status code so this
    module never has to import anthropic to classify an error."""
    if isinstance(exc, LLMError):
        return False
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return status in _RETRYABLE_STATUS
    return any(cls.__name__ in _RETRYABLE_NAMES for cls in type(exc).__mro__)


def _parse_json(text: str) -> Dict[str, Any]:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.S)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
    raise LLMError("model did not return valid JSON: %s" % cleaned[:300])


def complete(
    role: str,
    system: str,
    user: str,
    max_tokens: int = 800,
    json_mode: bool = False,
    model: Optional[str] = None,
) -> Union[str, Dict[str, Any]]:
    """One Claude turn for ``role``. Returns str, or dict when json_mode."""
    model = model or model_for(role)
    if json_mode:
        system = _request_system(system, json_mode)

    if is_fake():
        out = _fake_response(role, system, user, json_mode)
        out_text = out if isinstance(out, str) else json.dumps(out)
        _record(role, model, _approx_tokens(system) + _approx_tokens(user), _approx_tokens(out_text))
        return out

    # Everything below this line bills. Each attempt reserves its worst case
    # before the request leaves the process, so a refusal costs nothing, a
    # failed attempt still counts, and concurrent callers cannot all spend the
    # same remaining dollar.
    if not _CLIENT.get("warned"):
        _CLIENT["warned"] = True
        logger.warning(
            "LLM_FAKE is not set: billing real Anthropic calls (first one: role=%s model=%s)", role, model
        )
    # Validated before the first reservation: an invalid config bills nothing.
    output_config = _effort_param(role)
    # Thinking cannot be disabled on claude-opus-5-5 and counts toward
    # max_tokens, so the request carries headroom on top of the reply cap.
    api_max_tokens = reserved_output_tokens(max_tokens)
    client = _client()
    attempt = 0
    while True:
        attempt += 1
        reservation = enforce_budget(role, model, system, user, api_max_tokens)
        reserved = float(reservation["reserved_usd"])
        try:
            resp = client.messages.create(
                model=model,
                max_tokens=api_max_tokens,
                system=system or "",
                messages=[{"role": "user", "content": user}],
                # No ``thinking`` kwarg: on claude-opus-5-5 anything but
                # adaptive is a 400. Effort is sent explicitly because the
                # model's default is ``medium``.
                output_config=output_config,
            )
        except Exception as exc:  # noqa: BLE001 - re-raised below unless retried
            # The reservation stays charged: whether a failed request was
            # billed is unknowable from here, and the ceiling errs high.
            if attempt < MAX_ATTEMPTS and _is_retryable(exc):
                delay = RETRY_BACKOFF_SECONDS[min(attempt - 1, len(RETRY_BACKOFF_SECONDS) - 1)]
                logger.warning("llm attempt %d/%d failed (%s: %s); retrying in %.1fs",
                               attempt, MAX_ATTEMPTS, type(exc).__name__, exc, delay)
                _sleep(delay)
                continue
            raise
        break
    usage = getattr(resp, "usage", None)
    input_tokens = getattr(usage, "input_tokens", 0) or 0
    output_tokens = getattr(usage, "output_tokens", 0) or 0
    # Reconcile the reservation to what the response says it cost. A response
    # with no usage keeps the reservation: unknown cost is charged at worst case.
    if usage is not None:
        delta = round(estimate_cost(model, input_tokens, output_tokens) - reserved, 6)
        if delta:
            _add_spend(delta, to_store=reservation["reserved_in_store"])
    _record(role, model, input_tokens, output_tokens)
    stop_reason = getattr(resp, "stop_reason", None)
    if stop_reason == "refusal":
        raise LLMError("model refused (role=%s, model=%s)" % (role, model))
    if stop_reason == "max_tokens":
        # A truncated draft reads as finished and the cadence auto-sends it
        # after a 30-minute veto window, so the lead gets a half-written email.
        raise LLMError(
            "model output was cut off at max_tokens=%d (reply cap %d + thinking headroom %d; "
            "role=%s, model=%s); raise max_tokens or shorten the prompt"
            % (api_max_tokens, int(max_tokens), THINKING_HEADROOM_TOKENS, role, model)
        )
    text = "".join(getattr(block, "text", "") for block in resp.content if getattr(block, "type", "") == "text")
    if json_mode:
        return _parse_json(text)
    return text
