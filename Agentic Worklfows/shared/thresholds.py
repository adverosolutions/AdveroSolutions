"""Every Section 6, M1, M2, M4 and M5 number the marketing tier acts on.

That is the five-level deliverability monitor (Blueprint M1, O1, O5, O7), the
capacity inventory (M2), the campaign verdicts and copy experiments (M4, M3.3)
and the list factory's cost cap and weekly target (M5, Section 6 "cost per
verified lead"). It also holds the inbox-action apply script's ``email_list``
floors, the monitor's weekday schedule, the proposal severity order and two
small helpers (``rate_pct``, ``domain_of``).

The marketing-tier modules (``jobs/deliverability_monitor.py``,
``jobs/inbox_placement.py``, ``jobs/autoresponder_canary.py``,
``jobs/inbox_inventory.py``, ``jobs/campaign_verdicts.py``,
``jobs/list_factory.py``, ``shared/analytics.py``, ``services/experiments/``
and ``services/list_factory/``) must not carry a copy of one of these, under
its own name or any other: a local constant binds to this module
(``WARMUP_HEALTH_FLOOR = TH.WARMUP_HEALTH_MIN_PCT``).
``jobs/tests/test_threshold_bindings.py`` checks the VALUES of its ``WATCHED``
list (the Section 6 KPI, M1 placement and canary, M4 verdict and M5 cost and
target lines), so a renamed copy is caught as well as an identical one. It
scans module-level and class-level assignments and function defaults, not
literals inside function bodies, and a number that only collides by value is
allowlisted there with its reason. A number
inlined in a branch is a number nobody can find when Lorenzo asks "why did it
pause that inbox", and it is a number that silently disagrees with the twin
copy three functions down. The thresholds carry a comment naming the
blueprint section they come from, and Eric Nowoslawski's figures say whether
they are *published* or an *observed practice* taken from the video
transcript, because the two deserve different confidence. API limits, chunk
sizes and the severity order are operational, not blueprint figures, and say
so where it matters.

    from shared import thresholds as TH
    if health < TH.WARMUP_HEALTH_MIN_PCT: ...

Python 3.9 compatible. No I/O: this module imports nothing but ``typing``,
so it can never fail to load in a job that is mid-incident.
"""
from typing import Dict, Tuple

# --------------------------------------------------------------------------
# Level 1 - warm-up health per inbox (M1 L1, Section 6 "Warm-up health")
# --------------------------------------------------------------------------

# Eric, published: remove an inbox from rotation at 98%; never send below 90%.
# Section 6 KPI table: green >= 98, alert < 98 -> pause.
WARMUP_HEALTH_MIN_PCT = 98.0
# Below this an inbox is not merely proposed for pause, it is an emergency: the
# card is raised to high priority and the proposal says stop_sending.
WARMUP_HEALTH_EMERGENCY_PCT = 90.0

# POST /accounts/warmup-analytics accepts at most 100 emails per call (M1 L1,
# endpoint column). At 45 inboxes today and 45 + insurance later, one chunk is
# usually enough; the monitor chunks anyway so the 100th inbox does not silently
# fall off the report.
WARMUP_ANALYTICS_MAX_EMAILS_PER_CALL = 100
# POST /accounts/test/vitals has no documented cap. Same chunk size, for the
# same reason. Vitals answers grouped BY DOMAIN, not by account.
VITALS_MAX_ACCOUNTS_PER_CALL = 100

# A brand-new inbox has no warm-up history worth judging. Instantly reports
# health 100 from day one; an inbox younger than this is reported but never
# proposed for pause, because "pause the inbox you started warming yesterday"
# is the monitor eating its own insurance (M2: 33 inboxes started 2026-09-20).
WARMUP_MIN_AGE_DAYS_BEFORE_VERDICT = 7
# M2: warm-up runs 21 days before an inbox is promoted to sending.
WARMUP_DAYS_BEFORE_PROMOTION = 21

# The DNS records POST /accounts/test/vitals reports per domain. A missing one
# is a domain-level fault: every inbox on that domain is proposed for pause,
# because the fix is in DNS and pausing one inbox fixes nothing.
VITALS_REQUIRED_RECORDS = ("mx", "spf", "dkim", "dmarc")

# --------------------------------------------------------------------------
# Level 2 - inbox placement / seed tests (M1 L2, O5 Monday)
# --------------------------------------------------------------------------

# Eric, published: < 85% inbox placement on the seed test -> pause.
PLACEMENT_INBOX_MIN_PCT = 85.0
# M1 L2 action column: "Pause the failing inboxes; re-test after 48 h".
PLACEMENT_RETEST_HOURS = 48
# Instantly recipient_esp codes on POST /inbox-placement-analytics/stats-by-test-id.
# Only Google and Microsoft gate the verdict (M1 L2: "on Google or Microsoft
# seeds"); Web.de and Libero.it are reported and ignored.
PLACEMENT_ESP_CODES = {"google": 1, "microsoft": 2, "webde": 12, "libero": 13}  # type: Dict[str, int]
PLACEMENT_ESP_GATING = ("google", "microsoft")
# A placement percentage computed from a handful of seeds is noise. Below this
# many seed deliveries for an ESP the result is reported as "insufficient" and
# proposes nothing.
PLACEMENT_MIN_SEEDS_FOR_VERDICT = 5
# O5 runs weekly on Monday; a test older than this is stale and a new one is due.
PLACEMENT_TEST_MAX_AGE_DAYS = 7
# POST /inbox-placement-tests type: 0 = one-time, 1 = automated (M1 L2 names the
# automated type with a schedule and a placement_goes_below automation).
PLACEMENT_TEST_TYPE_ONE_TIME = 0
PLACEMENT_TEST_TYPE_AUTOMATED = 1
# sending_method: 0 = send from Instantly accounts, 1 = external SMTP.
PLACEMENT_SENDING_METHOD_INSTANTLY = 0

# --------------------------------------------------------------------------
# Level 3 - reply rate and bounce per inbox and per domain (M1 L3, O6 Friday)
# --------------------------------------------------------------------------

# Eric, published: >= 100 sent with < 1% real replies -> remove from rotation.
# "Real" excludes replies_automatic (auto-responders and OOO), which is exactly
# the field GET /accounts/analytics/daily returns beside `replies`.
REPLY_RATE_MIN_PCT = 1.0
REPLY_RATE_MIN_SENT = 100
# M1 L3 reads "in 7 d or 14 d": an inbox fails only when it has cleared the 100
# sent bar in a window AND missed 1% there. Both windows are computed; the
# verdict uses the longest window that has enough volume, so a slow inbox is
# judged on 14 days rather than declared innocent for lack of data.
REPLY_RATE_WINDOWS_DAYS = (7, 14)  # type: Tuple[int, ...]

# Whether `replies` on GET /accounts/analytics/daily already excludes
# `replies_automatic`. **It does on this workspace.** Measured read-only
# 2026-09-22 over 2026-09-15..21: lorenzo@myadvero.com reports replies=0 with
# replies_automatic=2, and lorenzo@proadvero.com replies=1 with
# replies_automatic=3, so the two are disjoint counters and subtracting one
# from the other yields a negative "real reply" count. Summed as-is the
# workspace totals are 22 real / 22 automatic on 1,800 sends = 1.2% each,
# which matches the figure Lorenzo measured by hand. M1 L3 says "exclude
# auto-replies" in words; on this API that means "use `replies`, do not
# subtract". Flip this to True only if a workspace is found where `replies` is
# the inclusive total, and re-measure before you do.
REPLIES_INCLUDE_AUTOMATIC = False

# Not Eric's, mine: the 1%-at-100-sends rule has a very wide error bar at low
# volume. At 150 sends, one extra reply moves an inbox from 0.67% to 1.33% and
# across the line. Below this many sends a level 3 failure is still proposed
# (the rule is the rule) but it is marked thin_evidence and demoted from high
# to medium severity, so Lorenzo can see which condemnations are really one
# coin flip wide.
REPLY_RATE_THIN_EVIDENCE_SENT = 300

# Eric, published: bounce > 2% -> remove. Section 6: green < 1%.
BOUNCE_RATE_MAX_PCT = 2.0
BOUNCE_RATE_GREEN_PCT = 1.0
# Same volume floor: 3 bounces out of 20 sends is 15% and means nothing.
# **This floor is judged on its own window.** The reply rule needs 100 sends;
# the bounce rule needs 50, and gating bounce behind the reply rule's volume
# made BOUNCE_RATE_MIN_SENT dead: an inbox at 80 sends and 10% bounce was
# discarded entirely. Level 3 now picks the longest window that clears THIS
# floor for the bounce verdict and the longest that clears REPLY_RATE_MIN_SENT
# for the reply verdict, then unions the failures.
BOUNCE_RATE_MIN_SENT = 50
# How close to BOUNCE_RATE_MAX_PCT counts as "sitting on the line" on the card.
# Three sending inboxes read exactly 2.00% on 2026-09-22: not a failure, but the
# difference between 2.00 and 2.01 is one bounce and Lorenzo should see it.
BOUNCE_RATE_AT_LINE_EPSILON_PCT = 0.05

# Section 6's Monday row is "Inbox placement test on a sample; bounce audit ->
# Placement < 85% or bounce > 2% -> pause", but the reply-rate audit is Friday.
# With the bounce verdict riding on the Friday run only, a domain that starts
# bouncing on a Saturday sends six more days of mail before anything notices.
# The 28-day daily pull happens every morning anyway, so the bounce half of
# level 3 is evaluated every day and the reply half stays on Friday.
BOUNCE_CHECK_EVERY_DAY = True

# M1 L3: "retire the domain if all its inboxes fail" and Eric's "never try to
# heal a domain". A domain is retired when this share of its inboxes fail; 1.0
# means every one of them, which is the rule as written.
DOMAIN_RETIRE_FAIL_RATIO = 1.0
# A domain with fewer live inboxes than this is not retired on a vote; the
# single-inbox domain would retire on one bad inbox.
DOMAIN_MIN_INBOXES_FOR_RETIRE = 2
# Retiring a domain is permanent, so it needs evidence a single inbox does not.
# At the measured fleet rate (1.06% per lead over 150 sends per inbox; 1.22%
# counting every reply) an individually healthy inbox reads under 1% about half
# the time (53%; 45% at 1.22%), so three of them on one domain do so about 15%
# of the time (9%) and at least one of four domains does on nearly half of all
# Fridays (a third), from noise alone. When True, a domain is only
# retired outright if EVERY failing inbox on it cleared
# REPLY_RATE_THIN_EVIDENCE_SENT; otherwise the proposal is still made, marked
# thin_evidence and demoted one severity step.
DOMAIN_RETIRE_REQUIRES_THICK_EVIDENCE = True

# GET /accounts/analytics/daily answers HTTP 413 on this workspace without an
# emails filter (verified read-only 2026-09-21, and again 2026-09-22 where the
# unfiltered call fell back to the 12 ids.json inboxes). 45 emails over 28 days
# did answer, but the failure mode is a whole silent report, so the monitor
# chunks. 25 keeps every call far inside the envelope that answered.
DAILY_ANALYTICS_CHUNK_EMAILS = 25
# Instantly shares 100 req/s and 6,000 req/min across the workspace; GET /emails
# alone is capped at 20 requests per minute. The canary harvest is the only
# caller that can approach it.
EMAILS_ENDPOINT_REQUESTS_PER_MINUTE = 20
# Pause between chunked analytics calls, seconds. Cheap insurance, not a limit.
API_CHUNK_SLEEP_SECONDS = 0.5

# --------------------------------------------------------------------------
# Level 4 - auto-responder canary (M1 L4, O7 Saturday)
# --------------------------------------------------------------------------

# Eric, observed practice (video transcript, not a published spec): expect
# >= 80% auto-responses; < 60% kills the inbox. Between the two is a warning.
CANARY_RESPONSE_TARGET_PCT = 80.0
CANARY_RESPONSE_KILL_PCT = 60.0
# How many harvested addresses each inbox mails in one canary round. This is a
# CEILING, not a quota: the round is clamped to what the harvested pool can
# cover without mailing anybody twice (see CANARY_MAX_SENDS_PER_ADDRESS).
CANARY_ADDRESSES_PER_INBOX = 10
# A response rate computed on fewer than this many delivered canaries is not a
# verdict. It is reported as "insufficient" and proposes nothing. It is also
# the floor below which a round is not planned at all: a pool that cannot give
# every inbox this many DISTINCT addresses is too small to canary the fleet.
CANARY_MIN_ADDRESSES_FOR_VERDICT = 5
# How many canary emails one harvested mailbox may receive in one round.
# **1 is the only safe value and this is not a tuning knob.** Round-robin over a
# short pool used to assign each of 29 mailboxes to 4 or 5 different inboxes, so
# one round put 4-5 near-identical notes into each real prospect's mailbox on the
# same day from 4-5 different Advero domains. At the Oct 11 target of 45 sending
# inboxes that would have been 18-19 each. That is the burst-from-many-domains
# pattern this whole monitor exists to avoid, aimed at mailboxes that already
# auto-reply and are the likeliest to be recycled or spam-trapped.
CANARY_MAX_SENDS_PER_ADDRESS = 1
# How long to wait for the auto-responders before scoring a round. Most fire in
# seconds; a few Exchange rules batch overnight.
CANARY_RESPONSE_WINDOW_HOURS = 24
# Subject patterns that identify an auto-responder in GET /emails?email_type=received.
# Case-insensitive substring match on the subject (M1 L4 endpoint column, plus
# the two variants seen live on 2026-09-22: "Out of office reply", "no longer in use").
AUTORESPONDER_SUBJECT_PATTERNS = (
    "automatic reply",
    "auto reply",
    "auto-reply",
    "out of office",
    "out-of-office",
    "no longer monitored",
    "no longer in use",
    "autoreply",
)
# How far back the harvest reads the received mailbox. The caller must check
# the walk's ``truncated`` flag: a partial harvest decides who gets mailed.
CANARY_HARVEST_MAX_PAGES = 5
# Page budget for GET /block-lists-entries. The blocklist is the one read that
# must never fail open, so this is generous and the caller refuses to plan when
# the walk is still truncated at this many pages (2 entries live on 2026-09-22;
# 50 pages is 5,000 entries).
BLOCKLIST_MAX_PAGES = 50
# A canary verdict older than this is history, not today's evidence. Without it
# one Saturday kill row re-proposed a high-severity pause every morning for the
# rest of the week, and forever if the canary never ran again.
CANARY_RESULT_MAX_AGE_DAYS = 7

# --------------------------------------------------------------------------
# Level 5 - positive-behaviour baseline campaign (M1 L5)
# --------------------------------------------------------------------------

# The baseline campaign is partner and peer outreach that SHOULD get replies.
# An inbox whose baseline reply rate halves against the campaign median takes a
# level 3 action (M1 L5 action column). The monitor never creates this campaign;
# it reads the spec file if it exists and reports "not configured" if it does not.
LEVEL5_SPEC_FILENAME = "level5_baseline_campaign.json"
LEVEL5_DROP_RATIO = 0.5
# Below this many sends an inbox has no baseline worth halving.
LEVEL5_MIN_SENT = 30
# GET /accounts/analytics/daily is per ACCOUNT, not per account and campaign, so
# until Instantly exposes that, level 5 measures the inbox's whole cold-outreach
# traffic rather than the baseline campaign's. That is a third of the evidence
# level 3 needs (LEVEL5_MIN_SENT 30 against REPLY_RATE_THIN_EVIDENCE_SENT 300)
# on a number the spec file itself calls directional, so a level 5 verdict may
# never outrank a level 3 one. Its proposals are capped at this severity and
# always carry thin_evidence until a per-campaign source exists.
LEVEL5_MAX_SEVERITY = "medium"

# --------------------------------------------------------------------------
# Sudden-drop alert (M1 alert row, runs daily with level 1)
# --------------------------------------------------------------------------

# "Any inbox/domain whose 7-day reply rate falls below 50% of its 4-week average
# (e.g. 1.5% -> 0.2%)".
SUDDEN_DROP_RATIO = 0.5
SUDDEN_DROP_RECENT_DAYS = 7
SUDDEN_DROP_BASELINE_DAYS = 28
# Without a baseline built on real volume, every quiet week looks like a
# collapse. The 4-week window must carry at least this many sends, and the
# baseline rate must be above this floor, or the check abstains.
SUDDEN_DROP_MIN_BASELINE_SENT = 100
SUDDEN_DROP_MIN_BASELINE_RATE_PCT = 0.5
# The 7-day window needs its own volume or a single quiet week reads as a drop.
SUDDEN_DROP_MIN_RECENT_SENT = 50
# Volume alone is not enough. At this workspace's reply rate (1.06% per lead,
# 1.22% counting every reply), 50 sends expects about 0.6 replies, so zero
# replies is the MODAL outcome and always reads as a 100% drop. The check
# therefore abstains unless the recent window expects at least this many
# replies at the baseline rate (baseline_pct/100 * recent_sent), which at a
# 1.06% baseline means roughly 470 sends in 7 days.
SUDDEN_DROP_MIN_EXPECTED_REPLIES = 5.0
# Owner decision R13 (2026-09-22): the sudden-drop alert is DOMAIN-ONLY for
# now. One inbox sends at most 150 a week (25/day, Mon-Sat; 125 on a Mon-Fri
# schedule), so expecting 5 replies needs a baseline of at least 3.3% (4.0% at
# 125), against a fleet at about 1%. The per-inbox check could therefore never
# fire, and a check that cannot fire must not look armed: with this False every
# inbox row abstains with that reason, and the card says "domain-only". A
# domain of three inboxes sends up to 450 a week and needs a baseline of about
# 1.1%, so the domain check stays. Redesigning the per-inbox check (a longer
# window or a Poisson test) is a separate decision for Lorenzo.
SUDDEN_DROP_PER_INBOX_ENABLED = False
# A drop measured on fewer recent sends than the level 3 thin-evidence floor is
# still reported, but demoted from critical to medium and marked thin: critical
# is the loudest thing this system says and it drives a high-priority push.
SUDDEN_DROP_THIN_EVIDENCE_SENT = REPLY_RATE_THIN_EVIDENCE_SENT
# How far back the bounce pull reaches when a drop fires (M1 alert: "pull last
# 24 h bounces").
BOUNCE_LOOKBACK_HOURS = 24
# What to look for in those bounces (M1 alert: "look for 550 / 'reported as spam'").
BOUNCE_SIGNATURES = (
    "550",
    "reported as spam",
    "spam",
    "blocked",
    "blacklist",
    "spamhaus",
    "5.7.1",
    "policy violation",
)
# Instantly's leads/list filter for bounced leads.
BOUNCED_LEADS_FILTER = "FILTER_VAL_BOUNCED"

# --------------------------------------------------------------------------
# Capacity and insurance (M2, used when proposing a replacement inbox)
# --------------------------------------------------------------------------

# M2: never more than 3 inboxes per domain. Enforced when the monitor picks an
# insurance inbox to swap in: a replacement that pushes a campaign's domain over
# the cap trades one deliverability problem for another.
MAX_INBOXES_PER_DOMAIN = 3
# The M2 reserve ratio (insurance >= 50% of active) is deliberately NOT here.
# On 2026-09-22 Lorenzo cut the inventory and the monitor to health alerts
# only: how many spare inboxes to hold, and when to buy more, is his decision,
# so no job counts a reserve or measures it against a floor.
# M2: 25 sends/day per inbox today; raise to 30 only on inboxes at >= 2% reply.
PER_INBOX_DAILY_LIMIT = 25
PER_INBOX_DAILY_LIMIT_RAISED = 30
# The campaigns send Mon-Sat (config/ids.json campaign_settings_observed), so
# one inbox's weekly ceiling is PER_INBOX_DAILY_LIMIT x this.
SENDING_DAYS_PER_WEEK = 6
REPLY_RATE_FOR_RAISED_LIMIT_PCT = 2.0

# --------------------------------------------------------------------------
# Campaign verdicts and copy experiments (M4, M3.3, Section 6), read by
# services/experiments/verdicts.py and experiment_log.py
# --------------------------------------------------------------------------

# M4: "No verdict before 1,000 sends; with >= 1 positive at 1,000, run to 3,000
# before deciding."
CAMPAIGN_VERDICT_MIN_SENDS = 1000
CAMPAIGN_CONFIRM_SENDS = 3000
# A campaign whose copy was reworked at the verdict line gets another 1,000
# sends before it is judged again.
CAMPAIGN_REWORK_RETEST_SENDS = CAMPAIGN_VERDICT_MIN_SENDS * 2
# M3.3 / M4: a variant is judged only at 500 sends or more per variant.
VARIANT_MIN_SENDS = 500
# Section 6 KPI "positive reply rate": green >= 0.7%, alert < 0.5% for 3 days.
POSITIVE_REPLY_RATE_GREEN_PCT = 0.7
POSITIVE_REPLY_RATE_ALERT_PCT = 0.5
# Significance line for a copy test. A tie-breaker on top of the 500-per-arm
# rule, never a licence to judge a smaller sample.
EXPERIMENT_ALPHA = 0.05

# --------------------------------------------------------------------------
# List factory cost KPI (M5, Section 6 "cost per verified lead"), read by
# services/list_factory/ledger.py
# --------------------------------------------------------------------------

# Section 6: cost per verified lead green at <= $0.02, alert at > $0.04. The
# list factory's hard stop halts a run whose projection breaks the cap below.
# The cap was $0.02 (Section 6's green line) until 2026-09-25. Lorenzo,
# 2026-09-25: raised to $0.07 because every model role now runs on Claude
# Opus 5.5 and the projection prices worst-case thinking (1,024 output tokens
# per call, shared.llm.output_tokens_with_thinking), which alone is about
# $0.02 per personalization line. Lower it again after measuring the first
# real run's thinking spend. The $0.04 alert line is unchanged, so a finished
# run between $0.04 and $0.07 still reports verdict "alert" (status over_cap).
LIST_FACTORY_MAX_COST_PER_CONTACT_USD = 0.07
LIST_FACTORY_ALERT_COST_PER_CONTACT_USD = 0.04
# M5: 3,300 verified contacts a week, the fleet-wide plan at 1,100+ sends a
# day. The default target of a single-niche run (jobs/list_factory.py,
# pipeline.Config); the --all-campaigns run sizes each campaign from
# config/list_factory_targets.json instead.
LIST_FACTORY_WEEKLY_TARGET = 3300

# --------------------------------------------------------------------------
# The apply script (changesets/inbox_actions/apply_inbox_actions.py)
# --------------------------------------------------------------------------

# A campaign patched down to fewer sending inboxes than this is not a campaign,
# it is an outage, and the apply refuses rather than "succeeding" into silence.
# The hard floor stays at 1 on purpose: raising it would make a legitimate
# removal on a two-inbox campaign impossible through the only tool allowed to
# execute one, which is how proposals end up being hand-edited in the UI with
# no diff, no backup and no audit row.
MIN_EMAIL_LIST_AFTER_APPLY = 1
# Below this the apply still runs but prints a loud capacity warning: at 25
# sends/day per inbox, a campaign under three inboxes is under 75/day.
WARN_EMAIL_LIST_AFTER_APPLY = 3

# --------------------------------------------------------------------------
# Schedule (Section 6 "Operating cadence"), America/Chicago
# --------------------------------------------------------------------------

LEVEL1_HOUR_CT = 7           # daily 07:00: level 1 + vitals + sudden drop (O1)
LEVEL2_WEEKDAY = 0           # Monday: inbox placement test (O5)
LEVEL3_WEEKDAY = 4           # Friday: reply-rate / bounce audit (O6 feeds off it)
LEVEL4_WEEKDAY = 5           # Saturday: auto-responder canary (O7)
# Levels that run every single day whatever the weekday is.
LEVELS_EVERY_DAY = (1, 5)


def _levels_for_weekday(weekday: int) -> Tuple[int, ...]:
    """Derived, not hand-written: a hand-written table drifts from the four
    weekday constants above and nobody notices until a Friday audit silently
    stops running."""
    levels = set(LEVELS_EVERY_DAY)
    if weekday == LEVEL2_WEEKDAY:
        levels.add(2)
    if weekday == LEVEL3_WEEKDAY:
        levels.add(3)
    if weekday == LEVEL4_WEEKDAY:
        levels.add(4)
    return tuple(sorted(levels))


# Which levels a given weekday runs when the monitor picks for itself.
# Note that the BOUNCE half of level 3 runs daily regardless (see
# BOUNCE_CHECK_EVERY_DAY); this table is about the full audit.
LEVELS_BY_WEEKDAY = {d: _levels_for_weekday(d) for d in range(7)}  # type: Dict[int, Tuple[int, ...]]

# --------------------------------------------------------------------------
# Proposal severities (how the card is ordered and how loud the push is)
# --------------------------------------------------------------------------

SEVERITY_ORDER = ("critical", "high", "medium", "low")
# Any proposal at or above this severity makes the ntfy push high priority.
NOTIFY_HIGH_PRIORITY_AT = "high"


def severity_rank(severity: str) -> int:
    """Index into SEVERITY_ORDER; unknown severities sort last."""
    try:
        return SEVERITY_ORDER.index(severity)
    except ValueError:
        return len(SEVERITY_ORDER)


def severities_at_or_above(severity: str) -> Tuple[str, ...]:
    """('critical', 'high') for 'high'. Used for the notify priority so
    NOTIFY_HIGH_PRIORITY_AT is a knob rather than a decoration."""
    return tuple(SEVERITY_ORDER[:severity_rank(severity) + 1])


def demote(severity: str) -> str:
    """One step quieter, floored at the least severe level."""
    return SEVERITY_ORDER[min(severity_rank(severity) + 1, len(SEVERITY_ORDER) - 1)]


def cap_severity(severity: str, ceiling: str) -> str:
    """The quieter of the two."""
    return severity if severity_rank(severity) >= severity_rank(ceiling) else ceiling


# Constants declared here that no job reads yet, each with the reason it is kept
# rather than deleted. ``test_thresholds_have_no_dead_constants`` asserts that
# every other public name in this module is referenced by at least one job, so a
# threshold nobody consults can never quietly become decoration again.
RESERVED_CONSTANTS = {
    # PER_INBOX_DAILY_LIMIT_RAISED and REPLY_RATE_FOR_RAISED_LIMIT_PCT used to
    # sit here as "declared but unread": raising a healthy inbox's limit is
    # M2/O8's decision, not the monitor's. jobs/inbox_inventory.py now reads
    # both (as RAMPED_DAILY_LIMIT and RAMP_MIN_REPLY_RATE), which is the right
    # owner, so they are no longer reserved. They had drifted into two units in
    # two files before that binding: 2.0 here and 0.02 there.
    # BOUNCE_LOOKBACK_HOURS used to be listed here as unread. It is not:
    # jobs/deliverability_monitor.py reads it as the default look-back of the
    # bounce pull that follows a sudden drop, so it was removed from this list.
}


def rate_pct(numerator: float, denominator: float) -> float:
    """Percentage, with 0 sends answering 0.0 rather than raising.

    Every rate in the monitor goes through this, so "no sends" can never be
    read as "0% reply rate, pause it".
    """
    try:
        denominator = float(denominator)
    except (TypeError, ValueError):
        return 0.0
    if not denominator:
        return 0.0
    try:
        return (float(numerator) / denominator) * 100.0
    except (TypeError, ValueError):
        return 0.0


def domain_of(email: str) -> str:
    """'lorenzo@theadvero.com' -> 'theadvero.com'. '' for anything unparseable."""
    if not email or "@" not in email:
        return ""
    return email.rsplit("@", 1)[1].strip().lower()
