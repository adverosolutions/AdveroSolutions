"""MKT-5: every Section 6, M4 and M5 number lives in ``shared/thresholds.py``.

``test_one_system.py`` catches a copy that keeps its name. This file catches
the copy that does not: ``WARMUP_HEALTH_FLOOR = 98`` in the inventory passed
that guard because the name differed. The scan works by VALUE: any
module-level or class-level assignment (also inside ``if``/``try``/``with``
blocks, through tuple unpacking, through simple arithmetic such as ``2 / 100``,
and inside dict, tuple, list and set literals), and any function default, in
the marketing-tier modules whose number equals a watched threshold, as a number
or as a percentage turned into a fraction, fails unless it is on the allowlist
below with the reason it is not that threshold. Watched: the Section 6 KPI
lines, the M1 placement and canary lines, the M4 verdict lines and the M5
cost and weekly-target lines.

The allowlist is the cost of matching by value: small numbers such as 1, 2
and 25 recur for unrelated reasons. A new entry has to say why the number is
not the threshold it collides with; "it is the threshold, renamed" is the
thing this test exists to refuse.

Not covered, on purpose: literals inside function bodies, call arguments and
expressions (``if p < 0.05``), and numbers hidden in strings. A scan
of those in the files below on 2026-09-22 found only coincidences (a 1000 in
"replies per 1k sends", a 300 in a capacity sanity check, a 0.7 confidence
floor), so they would be allowlist noise; the bindings are pinned by name in
the last tests instead.
"""
import ast
import glob
import os

import pytest

from shared import thresholds as TH

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Section 6 KPI lines, M4 verdict lines, M5 list-factory cost lines.
WATCHED = (
    "WARMUP_HEALTH_MIN_PCT", "WARMUP_HEALTH_EMERGENCY_PCT",
    "BOUNCE_RATE_MAX_PCT", "BOUNCE_RATE_GREEN_PCT", "BOUNCE_RATE_MIN_SENT",
    "REPLY_RATE_MIN_PCT", "REPLY_RATE_MIN_SENT", "REPLY_RATE_THIN_EVIDENCE_SENT",
    "REPLY_RATE_FOR_RAISED_LIMIT_PCT",
    "WARMUP_MIN_AGE_DAYS_BEFORE_VERDICT", "WARMUP_DAYS_BEFORE_PROMOTION",
    "PER_INBOX_DAILY_LIMIT", "PER_INBOX_DAILY_LIMIT_RAISED",
    "CAMPAIGN_VERDICT_MIN_SENDS", "CAMPAIGN_CONFIRM_SENDS", "CAMPAIGN_REWORK_RETEST_SENDS",
    "VARIANT_MIN_SENDS", "POSITIVE_REPLY_RATE_GREEN_PCT", "POSITIVE_REPLY_RATE_ALERT_PCT",
    "EXPERIMENT_ALPHA",
    "LIST_FACTORY_MAX_COST_PER_CONTACT_USD", "LIST_FACTORY_ALERT_COST_PER_CONTACT_USD",
    "LIST_FACTORY_WEEKLY_TARGET",
    # M1 L2 placement and M1 L4 canary lines (re-review: PLACEMENT_FLOOR = 85.0
    # and KILL_LINE = 60.0 passed the first version of this guard).
    "PLACEMENT_INBOX_MIN_PCT", "PLACEMENT_MIN_SEEDS_FOR_VERDICT", "PLACEMENT_RETEST_HOURS",
    "CANARY_RESPONSE_KILL_PCT", "CANARY_RESPONSE_TARGET_PCT", "CANARY_MIN_ADDRESSES_FOR_VERDICT",
    "CANARY_RESPONSE_WINDOW_HOURS", "CANARY_RESULT_MAX_AGE_DAYS",
)

SCANNED = [
    "jobs/list_factory.py", "jobs/inbox_inventory.py", "jobs/deliverability_monitor.py",
    "jobs/inbox_placement.py", "jobs/campaign_verdicts.py", "jobs/autoresponder_canary.py",
    "shared/analytics.py",
] + sorted(os.path.relpath(p, ROOT) for p in glob.glob(os.path.join(ROOT, "services", "experiments", "*.py"))) \
  + sorted(os.path.relpath(p, ROOT) for p in glob.glob(os.path.join(ROOT, "services", "list_factory", "*.py")))

# (file, name) -> why this number is not the threshold it happens to equal.
ALLOWED = {
    ("jobs/inbox_inventory.py", "ANALYTICS_RETRY_DEPTH"): "retry count for a 413'd analytics chunk",
    ("jobs/inbox_inventory.py", "ACCOUNT_STATUS_ACTIVE"): "Instantly account status code",
    ("jobs/deliverability_monitor.py", "ACCOUNT_STATUS_ACTIVE"): "Instantly account status code",
    ("jobs/deliverability_monitor.py", "ACCOUNT_STATUS_PAUSED"): "Instantly account status code",
    ("shared/analytics.py", "DEFAULT_CHUNK_EMAILS"): "emails per analytics call (HTTP 413 limit)",
    ("shared/analytics.py", "DEFAULT_CHUNK_SLEEP_SECONDS"): "pause between API chunks",
    ("shared/analytics.py", "DEFAULT_RETRY_DEPTH"): "retry count for a failed chunk",
    ("shared/analytics.py", "DEFAULT_TTL_SECONDS"): "cache lifetime in seconds",
    ("services/experiments/analytics.py", "ACTIVE_CAMPAIGN_STATUS"): "Instantly campaign status code",
    ("services/list_factory/contacts.py", "DEFAULT_MAX_VERIFY_ERROR_RATE"):
        "verifier error share that stops a run, not a statistical alpha",
    ("services/list_factory/icp.py", "DEFAULT_MAX_ESCALATIONS"): "Sonnet escalations per run",
    ("services/list_factory/icp.py", "TOKENS_OUT_PER_BUSINESS"): "LLM output tokens per business",
    ("services/list_factory/state.py", "DEFAULT_CHECKPOINT_EVERY"): "leads between state checkpoints",
    ("services/list_factory/suppression.py", "MAX_BLOCKLIST_PAGES"): "cursor page cap",
    ("services/list_factory/suppression.py", "MAX_EMAIL_PAGES"): "cursor page cap",
    ("services/list_factory/personalize.py", "MIN_CHARS"): "shortest acceptable personalization line",
    ("services/list_factory/ledger.py", "MIN_OBSERVED_SAMPLE_LEADS"):
        "verified leads before the observed rate replaces the plan's (a sample size)",
    ("services/experiments/copy_validator.py", "MAX_SENTENCE_WORDS"): "readability line, words per sentence",
    # whole literal tables (dict / tuple entries), allowlisted by table name
    ("jobs/deliverability_monitor.py", "KIND_COMPLETENESS"): "share of a proposal's actions that is executable",
    ("services/experiments/analytics.py", "OPEN_POSITIVE_STATUSES"): "Instantly interest-status codes",
    ("services/list_factory/ledger.py", "PRICES"): "vendor unit prices in USD, not the cost KPI",
    ("services/list_factory/ledger.py", "DEFAULT_PROJECTION_RATES"): "measured pipeline yield rates",
    ("services/list_factory/pipeline.py", "DEFAULT_RATES"): "measured pipeline yield rates",
    ("services/list_factory/pipeline.py", "SOURCE_NAME_RATES"): "share of source rows that carry a name",
    ("services/list_factory/sources.py", "SHARD_WEIGHTS"): "relative size of each state shard",
    ("services/list_factory/suppression.py", "DEFAULT_MAX_AGE_HOURS"):
        "age at which a suppression list is stale, not the canary response window",
    # function defaults: (file, "function.arg")
    ("jobs/list_factory.py", "_fail.rc"): "process exit code",
    ("jobs/inbox_placement.py", "list_tests.limit"): "API page size",
    ("jobs/autoresponder_canary.py", "resolve_interest_statuses.batch"): "lead lookups per call",
    ("services/list_factory/contacts.py", "__init__.ok_multiplier"): "verifier cost multiplier",
    ("services/list_factory/ledger.py", "count.n"): "increment",
    ("services/list_factory/pipeline.py", "__init__.min_staged_share"): "share of the target a run must stage",
    ("services/list_factory/sources.py", "niche_fill_rate.default"): "fallback fill rate for a source",
    ("services/list_factory/state.py", "tick.n"): "increment",
}


def _watched_values():
    out = {}
    for name in WATCHED:
        value = float(getattr(TH, name))
        out.setdefault(value, []).append(name)
        if name.endswith("_PCT"):
            out.setdefault(value / 100.0, []).append(name + " / 100")
    return out


def _num(node):
    """The number a literal expression evaluates to, or None. Folds the simple
    arithmetic a copy hides behind (``2 / 100``, ``-0.5``)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) \
            and not isinstance(node.value, bool):
        return float(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        inner = _num(node.operand)
        if inner is None:
            return None
        return -inner if isinstance(node.op, ast.USub) else inner
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Mult, ast.Div, ast.Add, ast.Sub)):
        left, right = _num(node.left), _num(node.right)
        if left is None or right is None:
            return None
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            return left / right if right else None
        return left + right if isinstance(node.op, ast.Add) else left - right
    return None


def _numbers_in(node, label):
    """``[(label, value)]`` for the value itself and every number inside a
    literal dict, tuple, list or set, recursively (``SECTION6 = {'warmup': 98,
    'bounce': 0.02}`` passed the first version of this guard)."""
    value = _num(node)
    if value is not None:
        return [(label, value)]
    out = []
    if isinstance(node, ast.Dict):
        for key, item in zip(node.keys, node.values):
            name = key.value if isinstance(key, ast.Constant) else "?"
            out.extend(_numbers_in(item, "%s[%r]" % (label, name)))
    elif isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        for i, item in enumerate(node.elts):
            out.extend(_numbers_in(item, "%s[%d]" % (label, i)))
    return out


def _match(value, watched):
    for key, names in watched.items():
        if abs(key - value) < 1e-9:
            return names
    return None


def _module_level_assignments(body):
    """Assignments at module or class level, including inside ``if``, ``try``,
    ``with`` and ``for`` blocks, but not inside functions (a function-local
    number is out of this guard's scope; see the module docstring)."""
    for node in body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            yield node
        elif isinstance(node, ast.ClassDef):
            for inner in _module_level_assignments(node.body):
                yield inner
        elif isinstance(node, (ast.If, ast.For, ast.While, ast.With)):
            for block in (node.body, getattr(node, "orelse", [])):
                for inner in _module_level_assignments(block):
                    yield inner
        elif isinstance(node, ast.Try):
            blocks = [node.body, node.orelse, node.finalbody] + [h.body for h in node.handlers]
            for block in blocks:
                for inner in _module_level_assignments(block):
                    yield inner


def _target_names(target):
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, (ast.Tuple, ast.List)):
        out = []
        for elt in target.elts:
            out.extend(_target_names(elt))
        return out
    return [ast.dump(target)]


def find_copies(source, path, watched=None):
    """``[(path, name, line, value, [threshold names])]`` for every literal
    number assigned at module or class level (bare, folded, or inside a dict,
    tuple, list or set literal), and every function default, that equals a
    watched threshold and is not allowlisted."""
    watched = watched if watched is not None else _watched_values()
    tree = ast.parse(source)
    hits = []
    for node in _module_level_assignments(tree.body):
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif node.value is not None:
            targets, value = [node.target], node.value
        else:
            continue
        for target in targets:
            names_here = _target_names(target)
            if isinstance(target, (ast.Tuple, ast.List)) and isinstance(value, (ast.Tuple, ast.List)) \
                    and len(target.elts) == len(value.elts):
                pairs = [(n, v) for n, v in zip(names_here, value.elts)]
            else:
                pairs = [(",".join(names_here), value)]
            for name, expr in pairs:
                for label, number in _numbers_in(expr, name):
                    names = _match(number, watched)
                    if not names:
                        continue
                    if (path, name) in ALLOWED or (path, label) in ALLOWED:
                        continue
                    hits.append((path, label, node.lineno, number, names))
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        args = node.args
        positional = args.args[len(args.args) - len(args.defaults):]
        pairs = list(zip(positional, args.defaults))
        pairs += [(a, d) for a, d in zip(args.kwonlyargs, args.kw_defaults) if d is not None]
        for arg, default in pairs:
            number = _num(default)
            if number is None:
                continue
            names = _match(number, watched)
            key = "%s.%s" % (node.name, arg.arg)
            if names and (path, key) not in ALLOWED:
                hits.append((path, key, node.lineno, number, names))
    return hits


def test_no_marketing_module_carries_a_renamed_threshold_copy():
    hits = []
    for rel in SCANNED:
        with open(os.path.join(ROOT, rel), "r", encoding="utf-8") as fh:
            hits.extend(find_copies(fh.read(), rel))
    assert not hits, "\n".join(
        "%s:%d %s = %r equals %s; bind it to shared.thresholds (or allowlist it with the reason it "
        "is a different number)" % (path, line, name, value, " / ".join(names))
        for path, name, line, value, names in hits)


@pytest.mark.parametrize("snippet", [
    # the re-review's misses
    "PLACEMENT_FLOOR = 85.0\n",
    "KILL_LINE = 60.0\n",
    "CANARY_KILL = 0.6\n",
    "SECTION6 = {'warmup': 98, 'bounce': 0.02}\n",
    "WEEKLY_TARGET = 3300\n",
    "LINES = (1000, 3000)\n",
    "A, B = 1000, 3000\n",
    "BOUNCE = 2 / 100\n",
    "import os\nif True:\n    FLOOR = 98\n",
    "try:\n    FLOOR = 98\nexcept Exception:\n    pass\n",
    "class X(object):\n    def f(self, alpha=0.05):\n        return alpha\n",
    # the first review's
    "WARMUP_HEALTH_FLOOR = 98\n",                    # the inventory copy the review found
    "BOUNCE_ALERT = 0.02\n",                          # a percentage turned into a fraction
    "VERDICT_LINE = 1000\n",
    "class X(object):\n    CONFIRM = 3000\n",
    "def judge(stats, alpha=0.05):\n    return alpha\n",
    "DEFAULT_MAX_COST_PER_CONTACT: float = 0.02\n",
    "POSITIVE_ALERT = 0.005\n",
])
def test_the_scan_catches_a_renamed_copy(snippet):
    assert find_copies(snippet, "jobs/some_new_module.py"), snippet


def test_every_allowlisted_entry_still_exists():
    """A stale allowlist entry would quietly excuse the next module that
    reuses the name."""
    seen = set()
    for rel in SCANNED:
        with open(os.path.join(ROOT, rel), "r", encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if getattr(target, "id", None):
                        seen.add((rel, target.id))
            elif isinstance(node, ast.AnnAssign) and getattr(node.target, "id", None):
                seen.add((rel, node.target.id))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for arg in node.args.args + node.args.kwonlyargs:
                    seen.add((rel, "%s.%s" % (node.name, arg.arg)))
    stale = sorted(k for k in ALLOWED if k not in seen)
    assert not stale, stale


# ------------------------------------------------ the bindings, pinned by name
def test_the_inventory_section6_lines_follow_thresholds(monkeypatch):
    from jobs import inbox_inventory as inv

    assert inv.WARMUP_HEALTH_FLOOR == TH.WARMUP_HEALTH_MIN_PCT
    assert inv.BOUNCE_ALERT == TH.BOUNCE_RATE_MAX_PCT / 100.0
    assert inv.REPLY_RATE_ALERT == TH.REPLY_RATE_MIN_PCT / 100.0
    assert inv.REPLY_RATE_MIN_SENT == TH.REPLY_RATE_MIN_SENT
    assert inv.WARMUP_SCORE_MATURE_DAYS == TH.WARMUP_MIN_AGE_DAYS_BEFORE_VERDICT
    assert inv.ANALYTICS_WINDOW_DAYS == TH.REPLY_RATE_WINDOWS_DAYS[0]


def test_the_m4_lines_follow_thresholds():
    from services.experiments import verdicts as V

    assert V.VERDICT_LINE == TH.CAMPAIGN_VERDICT_MIN_SENDS
    assert V.CONFIRM_LINE == TH.CAMPAIGN_CONFIRM_SENDS
    assert V.VARIANT_MIN_SENDS == TH.VARIANT_MIN_SENDS
    assert V.REWORK_RETEST_LINE == TH.CAMPAIGN_REWORK_RETEST_SENDS
    assert V.POSITIVE_GREEN == TH.POSITIVE_REPLY_RATE_GREEN_PCT / 100.0
    assert V.POSITIVE_ALERT == TH.POSITIVE_REPLY_RATE_ALERT_PCT / 100.0
    assert V.BOUNCE_ALERT == TH.BOUNCE_RATE_MAX_PCT / 100.0
    assert V.REAL_REPLY_FLOOR == TH.REPLY_RATE_MIN_PCT / 100.0


def test_the_experiment_alpha_follows_thresholds(monkeypatch):
    """Moving the threshold moves the decision: a p of 0.03 is a winner at
    alpha 0.05 and not at 0.01."""
    from services.experiments import experiment_log as EL

    assert EL.seed_document()["rules"]["alpha"] == TH.EXPERIMENT_ALPHA
    exp = {"metric": "positives"}
    observed = {"A": {"sends": 600, "positives": 12}, "B": {"sends": 600, "positives": 3}}
    gate = {"met": True, "rule": EL.RULE_PER_CAMPAIGN}
    p = EL._decide(exp, observed, "2026-10-20", gate)["p_value"]
    assert 0.01 < p < 0.05
    assert EL._decide(exp, observed, "2026-10-20", gate)["winner"] == "A"
    monkeypatch.setattr(TH, "EXPERIMENT_ALPHA", 0.01)
    assert EL._decide(exp, observed, "2026-10-20", gate)["winner"] is None


def test_the_list_factory_cost_lines_follow_thresholds():
    from services.list_factory import ledger

    assert ledger.DEFAULT_MAX_COST_PER_CONTACT == TH.LIST_FACTORY_MAX_COST_PER_CONTACT_USD
    assert ledger.ALERT_COST_PER_CONTACT == TH.LIST_FACTORY_ALERT_COST_PER_CONTACT_USD


@pytest.mark.parametrize("rel,inject", [
    ("jobs/inbox_placement.py", "\nPLACEMENT_FLOOR = 85.0\n"),
    ("jobs/autoresponder_canary.py", "\nKILL_LINE = 60.0\n"),
    ("jobs/inbox_inventory.py", "\nWARMUP_FLOOR_PCT = 98\n"),
    ("jobs/inbox_inventory.py", "\nSECTION6 = {'warmup': 98, 'bounce': 0.02}\n"),
    ("jobs/list_factory.py", "\nWEEKLY_TARGET = 3300\n"),
])
def test_the_reviewers_injected_copies_are_caught_in_the_real_files(rel, inject):
    """probe_guard2 from the re-review: each copy appended to the real module."""
    with open(os.path.join(ROOT, rel), "r", encoding="utf-8") as fh:
        src = fh.read() + inject
    assert find_copies(src, rel), inject


def test_the_m5_weekly_target_follows_thresholds():
    import jobs.list_factory as job
    from services.list_factory import pipeline

    assert job.DEFAULT_TARGET == TH.LIST_FACTORY_WEEKLY_TARGET
    assert pipeline.Config("cleaning", "cleaning_trigger").target == TH.LIST_FACTORY_WEEKLY_TARGET
