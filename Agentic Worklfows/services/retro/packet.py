"""Assemble the Friday retro packet (Blueprint O6, brief A10).

Generated, not written: the job runs, this builds a ``render.Packet``, and
Lorenzo spends ten minutes editing before he posts anything. The section order
follows Section 6 of the blueprint: numbers, then the deliverability audit and
the campaign verdicts, then what changed, then what the calls said, then the
three lessons, hours, and next week's three bets.

Two rules run through the whole file:
  - a number nobody measured is printed as "not available" with the reason,
    never as zero;
  - a claim the model made that the rubric rejected is printed in the appendix,
    not deleted, so the rubric is visible and can be argued with.
"""
import math
from typing import Any, Dict, List, Optional

from . import lessons as lessons_mod
from . import render
from . import sources as sources_mod
from .render import Packet, Section, fmt_delta, fmt_number, table

# Section 6 verdict lines.
VERDICT_SENDS = (1000, 3000)
INBOX_MIN_SENDS = 100
INBOX_MIN_REAL_REPLY_RATE = 0.01
INBOX_MAX_BOUNCE_RATE = 0.02

# 95% two-sided normal quantile, used for the Wilson interval below.
WILSON_Z = 1.96

OWNERS = ("Lorenzo",)


def _pct(value):
    return render.NOT_AVAILABLE if value is None else "%.2f%%" % (value * 100.0)


def wilson_bounds(successes, trials, z=WILSON_Z):
    # type: (float, float, float) -> Any
    """(lower, upper) 95% Wilson score interval for a proportion, or (None, None).

    The Section 6 lines are rules about an inbox's true rate, and a week of 100
    sends cannot measure a 1% rate: at 100 sends the line IS one reply, so a
    genuinely healthy 1.2% inbox shows zero about 30% of the time. Wilson is
    used instead of the point estimate because it behaves at zero successes and
    at small n, where the normal approximation does not. An inbox is only
    called a removal when the interval clears the line, so the verdict says
    "the data supports this", not "the coin came up tails".
    """
    n = float(trials or 0)
    if n <= 0:
        return (None, None)
    p = float(successes or 0) / n
    z2 = z * z
    denominator = 1.0 + z2 / n
    centre = (p + z2 / (2.0 * n)) / denominator
    margin = (z * math.sqrt(p * (1.0 - p) / n + z2 / (4.0 * n * n))) / denominator
    return (max(0.0, centre - margin), min(1.0, centre + margin))


# ------------------------------------------------------------- deliverability
def inbox_verdicts(rows, window_label="the audit window"):
    # type: (List[List[Any]], str) -> List[Dict[str, Any]]
    """Section 6 Friday audit, with a denominator big enough to mean something.

    The rule is "at least 100 sent and under 1% real replies, or a bounce rate
    over 2%, is a remove". Applied to the point estimate over one partial week
    it fired on 5 of 12 inboxes on the recorded week that the workspace
    measured at 1.2% replies and 1.2% bounces with nothing failing a threshold,
    which is a standing instruction to retire 42% of the sending capacity every
    Friday. Three of those five had "a real reply rate of 0.00%" on 100 sends,
    where the expected number of replies is 1.2; two had "3.00%" bounces on 3
    bounces out of 100.

    So the verdict is only "remove" when the 95% Wilson interval clears the
    line in the direction of removal:

      - replies: the UPPER bound is still under 1%, so even the optimistic
        reading fails. 0 replies on 100 sends has an upper bound of 3.7% and
        reads "watch"; 0 on 400 has an upper bound of 0.95% and reads "remove".
      - bounces: the LOWER bound is still over 2%, so even the charitable
        reading fails. 3 of 100 has a lower bound of 1.03% and reads "watch";
        20 of 400 has a lower bound of 3.26% and reads "remove".

    "watch" is the honest middle: the point estimate crosses the line and the
    data does not yet support acting on it. ``collect.audit_window`` widens the
    denominator to the trailing pull (about twelve days) so that middle empties
    out over time instead of sitting there forever.
    """
    out = []
    for row in rows or []:
        email, sent, bounced, bounce_rate, real, real_rate = row
        sent = float(sent or 0)
        bounce_low, _ = wilson_bounds(bounced or 0, sent)
        _, reply_high = wilson_bounds(real or 0, sent)
        verdict = "ok"
        why = ""
        if sent < INBOX_MIN_SENDS:
            verdict = "not enough data"
            why = "%d sent in %s, the rule needs %d" % (int(sent), window_label, INBOX_MIN_SENDS)
        elif bounce_low is not None and bounce_low > INBOX_MAX_BOUNCE_RATE:
            verdict = "remove"
            why = "bounce rate %s on %d sent in %s, over 2%% even at the low end of the range (%s)" % (
                _pct(bounce_rate), int(sent), window_label, _pct(bounce_low))
        elif reply_high is not None and reply_high < INBOX_MIN_REAL_REPLY_RATE:
            verdict = "remove"
            why = "%d sent in %s and a real reply rate of %s, under 1%% even at the high end of " \
                  "the range (%s)" % (int(sent), window_label, _pct(real_rate), _pct(reply_high))
        elif bounce_rate is not None and bounce_rate > INBOX_MAX_BOUNCE_RATE:
            verdict = "watch"
            why = "bounce rate %s on %d sent, but %d bounces at this volume is inside the range " \
                  "of a healthy inbox (up to %s), so this is not yet a removal" % (
                      _pct(bounce_rate), int(sent), int(bounced or 0), _pct(bounce_low))
        elif real_rate is not None and real_rate < INBOX_MIN_REAL_REPLY_RATE:
            verdict = "watch"
            why = "real reply rate %s on %d sent, but %d replies at this volume is inside the " \
                  "range of a healthy inbox (up to %s), so this is not yet a removal" % (
                      _pct(real_rate), int(sent), int(real or 0), _pct(reply_high))
        out.append({"email": email, "sent": sent, "bounced": bounced, "bounce_rate": bounce_rate,
                    "real_replies": real, "real_reply_rate": real_rate,
                    "bounce_rate_low": bounce_low, "real_reply_rate_high": reply_high,
                    "verdict": verdict, "why": why})
    return out


def campaign_verdicts(totals):
    # type: (List[Dict[str, Any]]) -> List[Dict[str, Any]]
    """Campaign verdicts at the cumulative 1,000 and 3,000-send lines.

    Two rules, both of which this table got wrong once:

    **The real reply count is ``reply_count_unique``, full stop.** It is not
    ``reply_count_unique`` minus ``reply_count_automatic_unique``. This is the
    same double subtraction ``metrics.real_replies`` documents at length and
    the runbook forbids, and it made one document contradict itself: the
    Campaigns table printed 2.50% for "2026 Cleaning - Trigger Outbound" and
    this table printed 0.67% for the same campaign in the same run. Replayed at
    the 1,000-send line it labelled all six campaigns "kill or rewrite",
    including the two cleaning campaigns that produced 4 of 6 positives and 2
    of 3 booked calls. ``reply_count_automatic_unique`` gets its own column,
    exactly as the funnel table gives auto-responders their own row.

    **Blueprint M4: "with >=1 positive at 1,000, run to 3,000 before
    deciding."** A campaign that crossed 1,000 with a positive in it is not
    killed on a rate just under 1%; it runs to 3,000 and is judged there. Only
    a campaign at 1,000 with no positives at all gets the kill test early.
    ``total_opportunities`` was collected and displayed and never once read.
    """
    out = []
    for row in totals or []:
        sent = float(row.get("emails_sent_count") or 0)
        real = float(row.get("reply_count_unique") or row.get("reply_count") or 0)
        auto = float(row.get("reply_count_automatic_unique")
                     or row.get("reply_count_automatic") or 0)
        rate = (real / sent) if sent else None
        opportunities = float(row.get("total_opportunities") or 0)
        line = None
        for threshold in VERDICT_SENDS:
            if sent >= threshold:
                line = threshold
        under = rate is not None and rate < INBOX_MIN_REAL_REPLY_RATE
        if line is None:
            verdict = "no verdict yet"
            why = "%d sent, the first verdict line is %d" % (int(sent), VERDICT_SENDS[0])
        elif line == VERDICT_SENDS[0] and opportunities >= 1:
            verdict = "run to 3,000"
            why = "%d sent, a real reply rate of %s and %d positive(s); M4 says a campaign with a " \
                  "positive at 1,000 runs to 3,000 before a decision" % (
                      int(sent), _pct(rate), int(opportunities))
        elif under:
            verdict = "kill or rewrite"
            why = "%d sent, a real reply rate of %s and no positives" % (int(sent), _pct(rate))
        else:
            verdict = "keep"
            why = "%d sent and a real reply rate of %s" % (int(sent), _pct(rate))
        out.append({"name": row.get("campaign_name"), "sent": sent, "real_replies": real,
                    "auto_replies": auto, "real_reply_rate": rate,
                    "opportunities": row.get("total_opportunities"),
                    "verdict": verdict, "why": why})
    out.sort(key=lambda r: (-(r["real_reply_rate"] or 0), r["name"] or ""))
    return out


# ------------------------------------------------------------------ sections
def funnel_section(week):
    return Section(
        "Funnel, this week against last week",
        body="%s against %s." % (week.this_window.describe(), week.last_window.describe()),
        table=render.metric_table(week.funnel,
                                  this_label=week.this_window.start_date + " week",
                                  last_label=week.last_window.start_date + " week"),
    )


def campaign_section(week):
    rows = []
    for row in week.campaign_rows:
        name, sent, real, rate, last_sent, last_real, last_rate = row
        rows.append([name, fmt_number(sent), fmt_number(real), _pct(rate),
                     fmt_number(last_sent), fmt_number(last_real), _pct(last_rate),
                     fmt_delta(rate, last_rate, "%")])
    verdicts = campaign_verdicts(week.campaign_totals)
    verdict_rows = [[v["name"], fmt_number(v["sent"]), fmt_number(v["real_replies"]),
                     _pct(v["real_reply_rate"]), fmt_number(v["auto_replies"]),
                     fmt_number(v["opportunities"]), v["verdict"], v["why"]] for v in verdicts]
    sections = [
        Section(
            "Campaigns",
            table=table(["Campaign", "Sent", "Real replies", "Real reply rate",
                         "Sent (last)", "Real replies (last)", "Rate (last)", "Change"], rows)
            if rows else None,
            note="No per-campaign data was returned." if not rows else None,
        ),
        Section(
            "Campaign verdicts (cumulative, Section 6)",
            body="Verdict lines are at 1,000 and 3,000 lifetime sends. Lifetime totals come from "
                 "campaigns/analytics with no date range, which is the only thing that endpoint "
                 "reports correctly. Real replies are reply_count_unique; auto-responders are a "
                 "separate counter and are never subtracted from it. M4: a campaign with at least "
                 "one positive at 1,000 runs to 3,000 before it is judged.",
            table=table(["Campaign", "Lifetime sent", "Real replies", "Real reply rate",
                         "Auto-responders", "Opportunities", "Verdict", "Why"], verdict_rows)
            if verdict_rows else None,
            note="No campaign totals were returned." if not verdict_rows else None,
        ),
    ]
    return sections


def inbox_section(week):
    audit = getattr(week, "audit_window", week.this_window)
    label = "%s to %s" % (audit.start_date, audit.end_date)
    verdicts = inbox_verdicts(week.inbox_rows, window_label=label)
    rows = [[v["email"], fmt_number(v["sent"]), fmt_number(v["bounced"]), _pct(v["bounce_rate"]),
             fmt_number(v["real_replies"]), _pct(v["real_reply_rate"]), v["verdict"], v["why"]]
            for v in verdicts]
    removes = [v for v in verdicts if v["verdict"] == "remove"]
    watches = [v for v in verdicts if v["verdict"] == "watch"]
    notes = []
    if removes:
        notes.append(
            "%d inbox(es) cross a Section 6 line over %s: %s. Nothing is paused by this job; that "
            "is A4's deliverability monitor, and it needs your approval." % (
                len(removes), label, ", ".join(v["email"] for v in removes)))
    if watches:
        notes.append(
            "%d inbox(es) are on watch: the point estimate is over the line but the volume behind "
            "it does not support a removal yet (%s)." % (
                len(watches), ", ".join(v["email"] for v in watches)))
    if not removes and not watches and rows:
        notes.append("No inbox crosses a Section 6 line over %s." % label)
    return Section(
        "Inbox and domain audit",
        body="Per inbox over %s, not over the retro week. One week of 25 sends a day is about 100 "
             "sends an inbox, where the 1%% reply line is a single reply and a healthy inbox reads "
             "\"remove\" roughly a third of the time. The rule needs %d sent, and it only calls a "
             "removal when the 95%% range clears the line." % (
                 audit.describe(), INBOX_MIN_SENDS),
        table=table(["Inbox", "Sent", "Bounces", "Bounce rate", "Real replies",
                     "Real reply rate", "Verdict", "Why"], rows) if rows else None,
        note=" ".join(notes) or ("No per-inbox data was returned." if not rows else None),
    )


def changes_section(week):
    notable = week.changes.get("notable") or []
    rolled = week.changes.get("rolled_up") or {}
    bullets = ["`%s` %s (%s)" % (c["hash"][:7], c["subject"], (c.get("date") or "")[:10])
               for c in notable[:40]]
    for prefix, count in rolled.items():
        bullets.append("%d x %s commits, rolled up" % (count, prefix))
    audit = week.sources.get("audit_logs")
    if audit and audit.ok:
        # sources.audit_logs has already dropped every entry outside the window.
        # It did not used to, and a handoff file staged once in July then listed
        # a campaign pause and an account delete from 2026-07-04 under "System
        # changes in the window" of every retro after it.
        for system in ("instantly", "ghl"):
            for entry in (audit.value or {}).get(system, [])[:20]:
                bullets.append("%s audit: %s %s %s" % (
                    system, entry.get("ts", ""), entry.get("action", ""), entry.get("target", "")))
    note = None
    if audit is None:
        note = "no audit log source"
    elif not audit.ok:
        note = audit.reason
    elif audit.reason:
        note = audit.reason
    return Section(
        "System changes",
        body="%d commit%s in %s." % (week.changes.get("total", 0),
                                     "" if week.changes.get("total", 0) == 1 else "s",
                                     week.this_window.describe()),
        bullets=bullets or ["No commits in the window."],
        note=note,
    )


def calls_section(week, proposal):
    calls = week.recaps.get("calls") or []
    bullets = ["%s %s%s" % (c.get("date"), c.get("title") or "call",
                            (" - " + c["url"]) if c.get("url") else "")
               for c in calls]
    wins = proposal.get("wins") or []
    objections = proposal.get("objections") or []
    sections = [Section(
        "Calls this week",
        body="%d recap emails in the window." % len(calls),
        bullets=bullets or ["No Fireflies recaps in the window."],
        note=week.recaps.get("note") or None,
    )]
    sections.append(Section(
        "Wins",
        bullets=["%s (%s)" % (w.get("text"), (w.get("source") or {}).get("section") or "call")
                 for w in wins] or ["Nothing the call notes support."],
    ))
    sections.append(Section(
        "Objections and open questions",
        bullets=["%s (%s)" % (o.get("text"), (o.get("source") or {}).get("section") or "call")
                 for o in objections] or ["Nothing the call notes support."],
    ))
    return sections


def lessons_section(proposal):
    lessons = proposal.get("lessons") or []
    bullets = []
    for lesson in lessons:
        bullets.append(
            "**%s %s.** %s (%s) Next: %s (%s)" % (
                lesson.get("metric"), lesson.get("number"), lesson.get("cause"),
                lesson.get("cite"), lesson.get("action"), lesson.get("owner")))
    notes = []
    if proposal.get("short"):
        notes.append(
            "The rubric accepted %d of the %d lessons asked for. What it rejected, and why, is in "
            "the appendix. Padding the list would defeat the point."
            % (len(lessons), lessons_mod.WANTED))
    if proposal.get("cached"):
        notes.append("These were written by an earlier run this week and re-judged against the "
                     "numbers above before being printed.")
    if proposal.get("numbers_changed"):
        notes.append("The funnel has moved since they were written, so anything that no longer "
                     "quotes a number this table prints is in the appendix.")
    if proposal.get("stale_dropped"):
        notes.append("%d stored item(s) no longer matched this week's numbers and were dropped."
                     % proposal["stale_dropped"])
    if proposal.get("skipped"):
        notes.append("No model call was made: %s." % proposal["skipped"])
    if proposal.get("not_claimed"):
        notes.append("The week was not claimed in the store (%s), so the next run will ask again."
                     % proposal["not_claimed"])
    if proposal.get("error"):
        notes = ["The model call failed (%s), so there are no lessons this week." %
                 proposal["error"]]
    note = " ".join(notes) or None
    return Section(
        "Three lessons from the data",
        body="Proposed by the weekly model run and judged against the rubric in "
             "runbooks/retro.md. A lesson that does not name a number that moved, a change that "
             "plausibly caused it and a next action is thrown out.",
        bullets=bullets or ["No lesson passed the rubric this week."],
        note=note,
    )


def hours_section(week):
    source = week.rize
    if source is None or not source.ok or not source.value:
        return Section(
            "Hours by category",
            bullets=["Not available."],
            note=(source.reason if source else "no Rize export configured"),
        )
    total = sum(source.value.values()) or 1.0
    rows = [[category, "%.1f h" % hours, "%.0f%%" % (100.0 * hours / total)]
            for category, hours in sorted(source.value.items(), key=lambda kv: -kv[1])]
    rows.append(["Total", "%.1f h" % sum(source.value.values()), "100%"])
    return Section(
        "Hours by category",
        body="From the Rize export at %s." % source.origin,
        table=table(["Category", "Hours", "Share"], rows),
        note=source.reason or None,
    )


def bets_section(proposal, next_week_dates):
    bets = proposal.get("bets") or []
    rows = [[b.get("bet"), b.get("owner"), b.get("target"), b.get("metric"), b.get("by")]
            for b in bets]
    note = None
    if proposal.get("short") and len(bets) < lessons_mod.WANTED:
        note = "The rubric accepted %d of %d bets. The rest are in the appendix." % (
            len(bets), lessons_mod.WANTED)
    return Section(
        "Next week's three bets",
        body="Next week runs %s to %s. Every bet has one owner, one number and one date, and is "
             "scored against a funnel metric in next Friday's packet." % (
                 next_week_dates[0] if next_week_dates else "?",
                 next_week_dates[-1] if next_week_dates else "?"),
        table=table(["Bet", "Owner", "Target", "Measured by", "By"], rows) if rows else None,
        bullets=None if rows else ["No bet passed the rubric this week."],
        note=note,
    )


def turned_off_bullets():
    """One line per job Lorenzo turned off (config/turned_off_jobs.json). They
    have no rows by design: shown as turned off, never as missing."""
    from shared import turned_off

    return ["%s: %s" % (name, turned_off.label(name)) for name in turned_off.names()]


def machine_section(week):
    source = week.job_log
    off = turned_off_bullets()
    if source is None or not source.ok:
        return Section("What the machine did",
                       bullets=["Not available."] + (["Turned off, run by hand: " + b for b in off]),
                       note=(source.reason if source else "no Job_Log"))
    rows = sources_mod.summarise_job_log(source.value)
    return Section(
        "What the machine did",
        body="Job_Log rows written in the window (%s)." % source.origin,
        table=table(["Job", "Runs", "Statuses"], rows) if rows else None,
        bullets=["Turned off, run by hand: " + b for b in off] or None,
        note="No Job_Log rows in the window." if not rows else None,
    )


def appendix_section(proposal):
    rejections = proposal.get("rejections") or []
    if not rejections:
        return None
    rows = [[r.get("kind"), r.get("index"), r.get("reason"),
             str(r.get("raw"))[:160]] for r in rejections]
    return Section(
        "Appendix: rejected by the rubric",
        body="Kept on purpose. If the rubric is wrong, this is where you see it.",
        table=table(["Kind", "#", "Why it was rejected", "What was proposed"], rows),
    )


# -------------------------------------------------------------------- packet
def build_internal_packet(week, proposal, next_week_dates=None):
    # type: (Any, Dict[str, Any], Optional[List[str]]) -> Packet
    next_week_dates = next_week_dates or []
    sections = [funnel_section(week)]
    sections.extend(campaign_section(week))
    sections.append(inbox_section(week))
    sections.append(changes_section(week))
    sections.extend(calls_section(week, proposal))
    sections.append(lessons_section(proposal))
    sections.append(hours_section(week))
    sections.append(bets_section(proposal, next_week_dates))
    sections.append(machine_section(week))
    appendix = appendix_section(proposal)
    if appendix is not None:
        sections.append(appendix)
    subtitle = "Generated %s CT. Edit, then post. Nothing here has been sent anywhere." % (
        week.now.strftime("%Y-%m-%d %H:%M"))
    return Packet(
        title="Retro packet, week of %s" % week.this_window.start_date,
        subtitle=subtitle,
        sections=sections,
        caveats=week.caveats,
        meta={"week": week.this_window.start_date, "generated_at": week.now.isoformat(),
              "model_calls": proposal.get("calls", 0)},
    )


# ------------------------------------------------------------- the Skool post
def skool_draft(week, proposal):
    # type: (Any, Dict[str, Any]) -> Dict[str, str]
    """The Maker School post, as a draft. Nothing posts it.

    Copy rules apply because the post is public: no em dashes, no exclamation
    marks, signed Lorenzo. The AI/automation word ban from the offer sheet does
    NOT apply here, because Maker School is a community of people building
    exactly that and the ban exists to keep it out of prospect email.
    """
    wanted = ("sent", "real_reply_rate", "positives", "booked")
    found = dict((key, week.metric(key)) for key in wanted)
    unmeasured = [key for key in wanted
                  if found[key] is None or found[key].this_week is None]
    lines = ["Week of %s." % week.this_window.start_date, ""]
    if unmeasured:
        # This is the one artefact from the retro that goes in front of other
        # people. A source that failed makes sum_daily return zeros, and
        # "Sent 0, 0 positives, 0 calls booked" posted in public is worse than
        # saying nothing: it is a false statement about the business, staged
        # for Lorenzo to paste.
        lines.append(
            "Holding this week's numbers back: %s did not come back from the source this run, and "
            "I am not going to post a number I did not measure." % ", ".join(
                (found[key].label if found[key] is not None else key) for key in unmeasured))
    else:
        lines.append("Sent %s, real reply rate %s, %s positives, %s calls booked." % (
            fmt_number(found["sent"].this_week),
            fmt_number(found["real_reply_rate"].this_week, "%"),
            fmt_number(found["positives"].this_week),
            fmt_number(found["booked"].this_week)))
    lines.extend(["", "What I learned:"])
    for lesson in (proposal.get("lessons") or [])[:3]:
        lines.append("- %s" % lesson.get("cause"))
    if not (proposal.get("lessons") or []):
        lines.append("- Nothing passed my own bar this week, so I am not going to invent one.")
    lines.append("")
    lines.append("Next week:")
    for bet in (proposal.get("bets") or [])[:3]:
        lines.append("- %s (%s by %s)" % (bet.get("bet"), bet.get("target"), bet.get("by")))
    if not (proposal.get("bets") or []):
        lines.append("- Bets go up once the numbers say something.")
    lines.append("")
    lines.append("Lorenzo")
    raw = "\n".join(lines)
    # Check BEFORE the substitution, not after. The job's copy guard ran on the
    # repaired text and could never fire, so a lesson carrying an em dash or an
    # exclamation mark was silently rewritten and reported as clean.
    repairs = render.check_copy(raw, ban_words=False)
    body = raw.replace(render.EM_DASH, "-").replace(render.EN_DASH, "-").replace("!", ".")
    return {
        "title": "Week of %s" % week.this_window.start_date,
        "body": body,
        "community": "Maker School",
        "copy_repairs": repairs,
    }
