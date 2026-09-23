"""O6, the Friday retro packet (brief A10).

    python3 jobs/retro_packet.py --dry-run
    python3 jobs/retro_packet.py --now
    python3 jobs/retro_packet.py --dry-run --as-of 2026-09-25T16:00:00-05:00
    python3 jobs/retro_packet.py --dry-run --fixtures
    python3 jobs/retro_packet.py --now --scorecard "Shining Armor Cleaning" \
        --campaigns cleaning_reactivation

Runs Friday 16:00 CT. Reads Instantly, GHL (when a token exists), the git log,
the Job_Log, a staged Fireflies pull and a Rize export; asks the expensive
model for three lessons and three bets; judges them against the rubric; writes
one markdown file under .tmp/retro/ and records the Maker School post as a
would_do.

Four things this job will not do, in any mode:
  - post to Skool. The would_do is the whole point: ten minutes of editing,
    then Lorenzo posts by hand.
  - write to Instantly, GHL or any other live system. It only reads.
  - bill the expensive model on a run that is advertised as safe. ``--dry-run``
    and ``--fixtures`` never reach Anthropic: the dry run reuses this week's
    stored answer if there is one and prints "the dry run did not pay" if there
    is not, ``--fixtures`` is offline by definition, and ``--scorecard`` skips
    the call because the client scorecard never renders lessons. ``--pay``
    makes a dry run bill deliberately, and it writes the claim when it does, so
    even that pays at most once a week.
  - bill a second model call in the same week. The week is claimed in the
    store, and a re-run reuses the stored proposal unless --refresh is passed.
    Before the call the store is probed for writability, because a claim that
    cannot be written is a cost cap that is not there.

And one it will not do twice: a re-run does not overwrite the markdown file
Lorenzo has been editing, and it does not stage a second Skool would_do for a
week that already has one.
"""
import argparse
import hashlib
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

if __package__ in (None, ""):  # run as a script: make "shared" importable
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared import job_log as job_log_mod  # noqa: E402
from shared import settings  # noqa: E402
from shared.job_log import log_run  # noqa: E402
from shared.notify import notify  # noqa: E402
from shared.paths import tmp_dir  # noqa: E402
from shared.settings import TZ  # noqa: E402
from shared.store import get_store  # noqa: E402

from services.retro import collect as collect_mod  # noqa: E402
from services.retro import fakes as fakes_mod  # noqa: E402
from services.retro import lessons as lessons_mod  # noqa: E402
from services.retro import packet as packet_mod  # noqa: E402
from services.retro import render as render_mod  # noqa: E402
from services.retro import scorecard as scorecard_mod  # noqa: E402
from services.retro.weeks import shift_days, week_key  # noqa: E402

logger = logging.getLogger("jobs.retro_packet")

JOB = "retro_packet"
FIXTURES_DIR = Path(__file__).resolve().parent.parent / "services" / "retro" / "fixtures"
LLM_CLAIM_PREFIX = "retro:proposal:"
SKOOL_CLAIM_PREFIX = "retro:skool:"
# A --fixtures run renders recorded (and partly synthetic) weeks with lessons
# from an offline stand-in. It used to write this week's canonical
# retro_<monday>.md, record a Skool would_do in the real shadow log and claim
# the week's Skool slot, all unstamped, so a replay looked like the real
# Friday packet. Now it is stamped on the packet and on the Skool body, written
# under .tmp/retro/replay/ as *.replay.md, and touches no log and no store.
REPLAY_STAMP = "FIXTURES REPLAY, NOT A REAL WEEK"
REPLAY_NOTE = ("%s. Recorded and synthetic numbers, lessons from an offline stand-in, not the "
               "model. Do not edit, post or quote this." % REPLAY_STAMP)
REPLAY_SUBDIR = "replay"


class ClaimNotWritable(RuntimeError):
    """The store cannot hold this week's claim, so the weekly cost cap is not
    there. Raised BEFORE the model call, never after it."""



# ---------------------------------------------------------------- clients
def _clients(dry_run, offline):
    """Instantly and GHL clients. ``--dry-run`` still reads: a dry run of a
    read-only job that reads nothing proves nothing. ``--fixtures`` is the
    offline switch."""
    if offline:
        return None, None
    instantly = None
    ghl = None
    try:
        from shared.instantly import default_client
        instantly = default_client()
    except Exception as exc:  # noqa: BLE001 - a missing key degrades, it does not crash
        logger.warning("Instantly client unavailable (%s); the funnel will be empty", exc)
    try:
        from shared.ghl import GHL

        ghl = GHL()
    except Exception as exc:  # noqa: BLE001
        logger.warning("GHL client unavailable (%s)", exc)
    return instantly, ghl


def load_fixtures(path=None):
    # type: (Optional[str]) -> Dict[str, Any]
    """The recorded week used by --fixtures and by the tests."""
    path = Path(path) if path else (FIXTURES_DIR / "week_2026-09.json")
    with open(str(path), "r", encoding="utf-8") as handle:
        return json.load(handle)


# ------------------------------------------------------------- the proposal
def _claim_key(week_start):
    return "%s%s" % (LLM_CLAIM_PREFIX, week_start)


def _skool_key(week_start):
    return "%s%s" % (SKOOL_CLAIM_PREFIX, week_start)


def next_week_dates_for(week):
    # type: (Any) -> List[str]
    """The seven dates of the week AFTER the week being reviewed.

    Derived from ``week.this_window.start``, not from ``week.now``. Deriving it
    from the clock ignored ``--weeks-back`` entirely: a packet titled "week of
    2026-09-14" told the model that next week ran 2026-09-28 to 2026-10-04, two
    weeks out, and ``validate_bet`` then threw out every correctly dated bet
    with "date is not inside next week". ``--weeks-back`` is the runbook's
    answer to a missed Friday, which is exactly when it fired.
    """
    start = shift_days(week.this_window.start, 7)
    return [shift_days(start, i).strftime("%Y-%m-%d") for i in range(7)]


def _fingerprint(context):
    # type: (Dict[str, Any]) -> str
    """A hash of the funnel values the lessons were judged against."""
    metrics = context.get("metrics") or {}
    payload = dict((key, [data.get("this_week"), data.get("last_week"), data.get("change")])
                   for key, data in metrics.items())
    blob = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:12]


def _build_context(week):
    from services.retro import metrics as metrics_mod
    from services.retro.render import fmt_delta, fmt_number

    return lessons_mod.build_context(
        funnel=week.funnel,
        moved_keys=[m.key for m in metrics_mod.moved(week.funnel)],
        changes=week.changes.get("notable") or [],
        recap_items=week.recaps.get("items") or [],
        campaign_rows=week.campaign_rows,
        thresholds=collect_mod.SECTION6_THRESHOLDS,
        fmt_number=fmt_number,
        fmt_delta=fmt_delta,
        owners=packet_mod.OWNERS,
    )


def _rejudge(proposal, context, next_week_dates, recap_items):
    # type: (Dict[str, Any], Dict[str, Any], List[str], List[Dict[str, Any]]) -> Dict[str, Any]
    """Re-run the rubric over a stored proposal against THIS run's numbers.

    The claim is keyed by the Monday, so a proposal written by a mid-week run
    (or by a ``--scorecard`` run, which used to pay for lessons it threw away)
    was handed back verbatim on Friday. The funnel table then said "Emails sent
    1200" while the lessons underneath quoted "sent 300", which is the one
    thing the rubric exists to prevent: the lessons section promises the number
    is quoted exactly as the table prints it.

    Anything that no longer validates is dropped into the appendix with the
    reason, rather than printed.
    """
    out = dict(proposal)
    rejections = list(out.get("rejections") or [])
    kept_lessons = []
    for index, lesson in enumerate(out.get("lessons") or []):
        reasons = lessons_mod.validate_lesson(lesson, context)
        if reasons:
            rejections.append({"kind": "lesson (stale)", "index": index,
                               "reason": "written earlier this week and no longer true of these "
                                         "numbers: %s" % "; ".join(reasons), "raw": lesson})
        else:
            kept_lessons.append(lesson)
    kept_bets = []
    for index, bet in enumerate(out.get("bets") or []):
        reasons = lessons_mod.validate_bet(bet, context, next_week_dates)
        if reasons:
            rejections.append({"kind": "bet (stale)", "index": index,
                               "reason": "written earlier this week and no longer valid: %s"
                                         % "; ".join(reasons), "raw": bet})
        else:
            kept_bets.append(bet)
    for field, kind in (("wins", "win"), ("objections", "objection")):
        kept = []
        for index, item in enumerate(out.get(field) or []):
            reasons = lessons_mod.validate_citation(item, recap_items)
            if reasons:
                rejections.append({"kind": "%s (stale)" % kind, "index": index,
                                   "reason": "; ".join(reasons), "raw": item})
            else:
                kept.append(item)
        out[field] = kept
    dropped = (len(out.get("lessons") or []) - len(kept_lessons)) + \
              (len(out.get("bets") or []) - len(kept_bets))
    out["lessons"] = kept_lessons
    out["bets"] = kept_bets
    out["rejections"] = rejections
    out["stale_dropped"] = dropped
    out["short"] = len(kept_lessons) < lessons_mod.WANTED or len(kept_bets) < lessons_mod.WANTED
    return out


def _probe_store(store, key):
    """Prove the store can hold the claim BEFORE anything is billed.

    The cap on the weekly Opus call is the claim. A store that silently refuses
    to write it is a cap that does not exist, and the old code caught the
    exception and logged a warning, so every run that Friday paid again. This
    raises instead, and it raises before the money is spent.
    """
    if store is None:
        return
    probe = "%s:probe" % key
    try:
        store.set(probe, {"ok": True})
        store.delete(probe)
    except Exception as exc:  # noqa: BLE001 - re-raised as a named failure
        raise ClaimNotWritable(
            "the retro claim cannot be written to the store (%s: %s), so there is nothing to stop "
            "the expensive model being billed again on the next run. Fix the store before running "
            "the retro." % (type(exc).__name__, str(exc)[:200]))


def get_proposal(week, store=None, complete=None, refresh=False, skip_llm=False, persist=True,
                 offline=False, may_pay=True):
    # type: (Any, Any, Any, bool, bool, bool, bool, bool) -> Dict[str, Any]
    """Three lessons and three bets, judged. One model call a week, at most.

    The week is claimed in the store, so a second run on the same Friday (a
    retry, a manual re-run beside the cron) reuses the stored proposal instead
    of billing Opus twice, and the stored proposal is re-judged against this
    run's numbers before it is used. ``--refresh`` overrides the claim.

    Four ways this returns without billing anything:
      ``skip_llm``   ``--no-llm`` and every ``--scorecard`` run: the client
                     scorecard renders ``week`` and never reads a proposal.
      ``offline``    ``--fixtures``: an offline replay reaches no API, which is
                     what the runbook and ``--help`` have always claimed.
      fake mode      ``LLM_FAKE=1``, which answers from a stand-in built from
                     the real context.
      ``may_pay``    False on a plain ``--dry-run``. A dry run reuses a claim
                     that has already been paid for and otherwise renders the
                     packet with the lessons section saying so. ``--pay`` turns
                     it on and also turns ``persist`` on, so a paying dry run
                     claims the week like a real one.
    """
    next_week_dates = next_week_dates_for(week)
    empty = {"lessons": [], "bets": [], "wins": [], "objections": [], "rejections": [],
             "calls": 0, "short": True, "next_week_dates": next_week_dates}

    if skip_llm:
        return dict(empty, skipped="the model call is disabled for this run")

    context = _build_context(week)
    fingerprint = _fingerprint(context)
    recap_items = week.recaps.get("items") or []

    from shared import llm as llm_mod

    # "Is this answer a real, billed one?" is a question about the process, not
    # about who passed the callable. Keying it on "complete is None" meant an
    # evidence run or a replay harness that injected its own stand-in while
    # LLM_FAKE=1 stored a fabricated proposal tagged faked=false, and the next
    # real run served three invented lessons and reported model_calls=0. A
    # process in fake mode never bills, whoever supplied the callable; and an
    # offline --fixtures run with nothing supplied answers from the recorded
    # context, which is equally not a paid answer.
    faked = llm_mod.is_fake() or (offline and complete is None)

    key = _claim_key(week_key(week.this_window))
    cached = None
    overwrite = False
    if store is not None:
        try:
            cached = store.get(key)
        except Exception as exc:  # noqa: BLE001 - a store problem must not bill twice by accident
            logger.warning("could not read the retro claim (%s)", exc)
    if cached and cached.get("faked") and not faked:
        # A claim written by an LLM_FAKE=1 run (a demo, an evidence run, a
        # replay) must never be served to a real one: the packet would print
        # invented lessons under Lorenzo's name and the Job_Log would say the
        # model ran. Drop it and pay for a real answer.
        logger.warning("ignoring a faked retro proposal cached for %s", key)
        cached = None
        # And overwrite it below. Leaving it in place would make set_if_absent
        # fail, and this run would hand back the very proposal it just rejected.
        overwrite = True
    if cached and not refresh:
        reused = _rejudge(dict(cached), context, next_week_dates, recap_items)
        reused["cached"] = True
        reused["next_week_dates"] = next_week_dates
        reused["numbers_changed"] = bool(
            cached.get("fingerprint") and cached["fingerprint"] != fingerprint)
        return reused

    if not may_pay and not faked:
        # The run that is advertised as safe stays safe. It says what it would
        # have cost rather than paying and throwing the answer away. This gate
        # is about the run, not about who supplied the callable: a dry run does
        # not ask the model, full stop.
        return dict(empty, skipped="this run does not pay for the model, and the week is not "
                                   "claimed yet; run --now, or --dry-run --pay, for lessons")

    if complete is None and faked and llm_mod.fake_for("retro") is None:
        # LLM_FAKE=1 with nothing registered for "retro" returns the library's
        # generic {"role": "retro", "fake": true} blob, which has no lessons in
        # it, so every offline run would render an empty packet. Answer from
        # this week's real context instead.
        #
        # This is a stand-in for THIS call, not a global registration. Putting
        # it in shared.llm's registry meant a second run in the same process
        # (a replay loop, an evidence script, --weeks-back after a normal run)
        # reused the first run's fake, which was built against the first week's
        # context and next-week dates, so every bet in the second packet was
        # rejected with "date is not inside next week". A test that registered
        # its own fake still wins: fake_for is how you tell.
        complete = _offline_complete(context, next_week_dates, recap_items)

    if complete is None and not llm_mod.is_fake():
        # About to spend money: prove the cap can be written first.
        _probe_store(store, key)

    proposal = lessons_mod.propose(context, next_week_dates, recap_items, complete=complete)
    proposal["next_week_dates"] = next_week_dates
    proposal["faked"] = faked
    proposal["fingerprint"] = fingerprint

    claimable = not proposal.get("error") and (proposal.get("lessons") or proposal.get("bets"))
    if store is not None and persist and claimable:
        try:
            if refresh or overwrite:
                store.set(key, proposal)
                wrote = True
            else:
                wrote = store.set_if_absent(key, proposal)
        except Exception as exc:  # noqa: BLE001 - re-raised as a named failure
            raise ClaimNotWritable(
                "the retro proposal for %s could not be written to the store (%s: %s). The answer "
                "has already been paid for and nothing is stopping the next run paying again."
                % (key, type(exc).__name__, str(exc)[:200]))
        if not wrote:
            # Someone claimed the week between the read and the write. Their
            # proposal is as good as this one and it is already paid for.
            existing = store.get(key)
            if existing:
                reused = _rejudge(dict(existing), context, next_week_dates, recap_items)
                reused["cached"] = True
                reused["next_week_dates"] = next_week_dates
                return reused
    elif store is not None and persist and not claimable:
        # A 529 from Anthropic is routine. Writing that failure into the store
        # as the week's answer meant one blip permanently emptied the section
        # the whole brief is about, and only --refresh could get it back.
        logger.warning("not claiming %s: the model call produced nothing usable (%s)",
                       key, proposal.get("error") or "no item passed the rubric")
        proposal["not_claimed"] = proposal.get("error") or "no item passed the rubric"
    return proposal


def _offline_complete(context, next_week_dates, recap_items):
    """``--fixtures`` with LLM_FAKE unset: answer from the recorded context.

    ``--fixtures`` is documented as an offline replay in the runbook table and
    in --help, and it reached Anthropic on every invocation. An offline replay
    that bills the most expensive model in the system is a trap, especially for
    a reviewer told to "run the job's --dry-run".
    """
    fake = fakes_mod.compliant(context, next_week_dates, recap_items)

    def complete(role, system, user, **kwargs):
        return fake(system, user, True)

    return complete


# -------------------------------------------------------------- the outputs
def stamp_replay(markdown):
    # type: (str) -> str
    """Put the replay stamp in the title and directly under it."""
    lines = markdown.split("\n")
    if lines and lines[0].startswith("# "):
        lines[0] = "# REPLAY: %s" % lines[0][2:]
        return "\n".join([lines[0], "", "> %s" % REPLAY_NOTE] + lines[1:])
    return "> %s\n\n%s" % (REPLAY_NOTE, markdown)


def write_markdown(text, week_start, out_dir=None, name="retro", now=None, force=False,
                   suffix=".md"):
    # type: (str, str, Optional[str], str, Optional[datetime], bool, str) -> Path
    """Write the packet, without destroying the one that is already there.

    The whole point of this job is ten minutes of hand editing, so the file it
    produces is the one thing a retry must not clobber. It used to open a fixed
    ``retro_<monday>.md`` with ``"w"``: re-running the job after an hour of
    editing silently replaced the edited file with a fresh render. A second run
    now writes ``retro_<monday>_<HHMMSS>.md`` beside it and says so; ``--force``
    is the way to overwrite on purpose.
    """
    directory = Path(out_dir) if out_dir else (tmp_dir() / "retro")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / ("%s_%s%s" % (name, week_start, suffix))
    if path.exists() and not force:
        stamp = (now or datetime.now(TZ)).strftime("%H%M%S")
        candidate = directory / ("%s_%s_%s%s" % (name, week_start, stamp, suffix))
        counter = 1
        while candidate.exists():
            candidate = directory / ("%s_%s_%s_%d%s" % (name, week_start, stamp, counter, suffix))
            counter += 1
        path = candidate
    with open(str(path), "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


def stage_skool_post(draft, week_start, path, store=None):
    # type: (Dict[str, str], str, Path, Any) -> Optional[Dict[str, Any]]
    """Record the Maker School post as a would_do. It is never sent.

    This deliberately does NOT go through ``settings.guard_write``. guard_write
    in live mode opens a ``live_write_intent`` Job_Log row that the caller is
    expected to close with ``live_write_ok`` or ``live_write_failed``. This job
    never posts, in any mode, so that row would hang open forever and every
    reconciliation would flag it. The would_do lands in the same shadow log
    through ``job_log.shadow`` instead, which is where every other would_do is
    read from.
    """
    payload = {
        "community": draft.get("community"),
        "title": draft.get("title"),
        "body": draft.get("body"),
        "week": week_start,
        "source_file": str(path),
        "posting": "manual, by Lorenzo, after editing",
    }
    if store is not None:
        # One would_do per week. Two runs on the same Friday used to leave two
        # skool/post_create records for the same week, and whoever posts from
        # the shadow log sees the same week twice with no way to tell which is
        # the one Lorenzo edited.
        try:
            if not store.set_if_absent(_skool_key(week_start), {"staged_at": path and str(path)}):
                logger.info("the Skool post for %s is already staged; not staging it again",
                            week_start)
                return None
        except Exception as exc:  # noqa: BLE001 - a store blip must not lose the draft
            logger.warning("could not claim the Skool would_do for %s (%s); staging anyway",
                           week_start, exc)
    record = job_log_mod.shadow("skool", "post_create", payload)
    return record or {"system": "skool", "action": "post_create", "payload": payload}


# ------------------------------------------------------------------- the run
def run(now, instantly=None, ghl=None, store=None, dry_run=False, weeks_back=0,
        fixtures=None, complete=None, refresh=False, skip_llm=False, out_dir=None,
        client=None, campaign_keys=None, repo=None, pay=False, force=False,
        job_log_path=None, replay=False):
    # type: (datetime, Any, Any, Any, bool, int, Optional[Dict[str, Any]], Any, bool, bool, Optional[str], Optional[str], Optional[List[str]], Optional[str], bool, bool, Optional[str]) -> Dict[str, Any]
    week = collect_mod.collect_week(
        now, instantly=instantly, ghl=ghl, weeks_back=weeks_back, fixtures=fixtures, repo=repo,
        job_log_path=job_log_path)
    offline = fixtures is not None
    # ``replay`` is what ``--fixtures`` on the CLI means: recorded numbers
    # standing in for a real week. Code that injects ``fixtures`` as a data
    # source (the tests) leaves it off and exercises the real write path.
    replay = bool(replay)
    # The client scorecard is rendered from ``week`` alone. Paying for three
    # lessons and three bets and then rendering a document that has no room for
    # either is one Opus call per client per week, bought and thrown away; with
    # --dry-run --scorecard it was not even cached, so every render paid again.
    wants_lessons = not client
    proposal = get_proposal(
        week, store=store, complete=complete, refresh=refresh,
        skip_llm=skip_llm or not wants_lessons,
        # A replay never claims the real week in the store.
        persist=((not dry_run) or pay) and not replay,
        offline=offline,
        may_pay=(not dry_run) or pay)
    next_week_dates = proposal.get("next_week_dates") or []

    summary = {
        "week": week.this_window.start_date,
        "mode": settings.get_mode(),
        "dry_run": bool(dry_run),
        "lessons": len(proposal.get("lessons") or []),
        "bets": len(proposal.get("bets") or []),
        "rejected": len(proposal.get("rejections") or []),
        "model_calls": proposal.get("calls", 0),
        "cached_proposal": bool(proposal.get("cached")),
        "sources": dict((k, v.ok) for k, v in week.sources.items()),
        "errors": list(week.errors),
        "caveats": list(week.caveats),
        "replay": replay,
    }  # type: Dict[str, Any]
    for field in ("skipped", "not_claimed", "stale_dropped", "numbers_changed"):
        if proposal.get(field):
            summary[field] = proposal[field]

    if client:
        card = scorecard_mod.build_client_scorecard(
            week, client_name=client, campaign_keys=campaign_keys)
        markdown = scorecard_mod.render_client_scorecard(card)
        name = "scorecard_%s" % "".join(
            c if c.isalnum() else "_" for c in client.lower())[:40]
    else:
        pkt = packet_mod.build_internal_packet(week, proposal, next_week_dates)
        markdown = render_mod.render_markdown(pkt)
        name = "retro"

    if replay:
        markdown = stamp_replay(markdown)
    summary["chars"] = len(markdown)
    if dry_run:
        summary["path"] = None
        summary["skool"] = None
        summary["markdown"] = markdown
        return summary

    suffix = ".replay.md" if replay else ".md"
    if replay:
        # Never the canonical retro_<monday>.md, and never the directory the
        # real packet lives in: --force on a replay used to overwrite the
        # packet Lorenzo had been editing.
        base = Path(out_dir) if out_dir else (tmp_dir() / "retro")
        target_dir = str(base / REPLAY_SUBDIR)
    else:
        target_dir = out_dir
    path = write_markdown(markdown, week.this_window.start_date, out_dir=target_dir, name=name,
                          now=now, force=force, suffix=suffix)
    summary["path"] = str(path)
    summary["kept_existing"] = not path.name.endswith(
        "_%s%s" % (week.this_window.start_date, suffix))
    summary["markdown"] = markdown
    if not client and replay:
        # A replay stages nothing: no shadow-log would_do, no Skool claim in
        # the store. The draft is returned stamped, for reading only.
        draft = packet_mod.skool_draft(week, proposal)
        body = "%s\n\n%s" % (REPLAY_NOTE, draft.get("body") or "")
        summary["skool"] = {"replay": True, "staged": False,
                            "payload": {"community": draft.get("community"),
                                        "title": "REPLAY: %s" % (draft.get("title") or ""),
                                        "body": body}}
    elif not client:
        draft = packet_mod.skool_draft(week, proposal)
        # skool_draft repairs em dashes and exclamation marks on its way out, so
        # checking the repaired body could never fail. The repairs it had to
        # make are what the guard is for, and they are reported here.
        problems = list(draft.get("copy_repairs") or [])
        problems.extend(render_mod.check_copy(draft["body"], ban_words=False))
        if problems:
            # A public post that breaks the copy rules is a defect, not a
            # warning: say so in the summary and in the Job_Log row.
            summary["skool_copy_problems"] = problems
        summary["skool"] = stage_skool_post(draft, week.this_window.start_date, path, store=store)
        if summary["skool"] is None:
            summary["skool_already_staged"] = True
    return summary


def _status(summary):
    if summary.get("errors"):
        return "errors"
    if summary.get("lessons", 0) < lessons_mod.WANTED and not summary.get("dry_run"):
        return "partial"
    return "ok"


def _print(summary):
    print("Retro packet, week of %s (mode=%s%s)" % (
        summary["week"], summary["mode"], ", dry-run" if summary["dry_run"] else ""))
    print("  lessons accepted: %d   bets accepted: %d   rejected by the rubric: %d" % (
        summary["lessons"], summary["bets"], summary["rejected"]))
    print("  model calls: %s%s" % (summary["model_calls"],
                                   " (reused this week's stored proposal)"
                                   if summary["cached_proposal"] else ""))
    if summary.get("skipped"):
        print("  no model call: %s" % summary["skipped"])
    if summary.get("not_claimed"):
        print("  the week was NOT claimed: %s" % summary["not_claimed"])
    if summary.get("stale_dropped"):
        print("  %d stored item(s) no longer matched this week's numbers and went to the appendix"
              % summary["stale_dropped"])
    if summary.get("numbers_changed"):
        print("  the stored proposal was written against different numbers earlier this week")
    if summary.get("skool_copy_problems"):
        print("  skool draft copy problems: %s" % "; ".join(summary["skool_copy_problems"]))
    bad = [name for name, ok in sorted(summary["sources"].items()) if not ok]
    if bad:
        print("  sources unavailable: %s" % ", ".join(bad))
    for caveat in summary["caveats"]:
        print("  caveat: %s" % caveat)
    if summary.get("path"):
        print("  written: %s" % summary["path"])
        if summary.get("kept_existing"):
            print("  an earlier file for this week was left untouched; use --force to overwrite")
        if summary.get("replay"):
            print("  replay: stamped, written under the replay folder, no Skool would_do "
                  "and no store claim")
        elif summary.get("skool"):
            print("  skool post: staged as a would_do, nothing was posted")
        elif summary.get("skool_already_staged"):
            print("  skool post: already staged for this week, not staged again")
    else:
        print("  dry run: nothing written")


def main(argv=None, now=None, store=None, complete=None):
    parser = argparse.ArgumentParser(description="O6 Friday retro packet")
    parser.add_argument("--dry-run", action="store_true",
                        help="read and render, write no file and stage no post")
    parser.add_argument("--now", action="store_true",
                        help="write the markdown file and stage the Skool post")
    parser.add_argument("--as-of", dest="as_of", default=None,
                        help="ISO timestamp to run at (default: now, CT)")
    parser.add_argument("--weeks-back", type=int, default=0,
                        help="regenerate an earlier week")
    parser.add_argument("--fixtures", action="store_true",
                        help="offline replay from services/retro/fixtures; reaches no API and "
                             "never bills the model")
    parser.add_argument("--fixtures-path", default=None)
    parser.add_argument("--refresh", action="store_true",
                        help="ask the model again even though this week is already claimed "
                             "(this costs money)")
    parser.add_argument("--pay", action="store_true",
                        help="let a --dry-run bill the model when the week is not claimed yet; it "
                             "then writes the claim too, so it still pays at most once a week")
    parser.add_argument("--force", action="store_true",
                        help="overwrite an existing markdown file for this week instead of writing "
                             "a second one beside it")
    parser.add_argument("--no-llm", action="store_true",
                        help="skip the model call entirely; render the numbers only")
    parser.add_argument("--out-dir", default=None)
    parser.add_argument("--scorecard", default=None, metavar="CLIENT",
                        help="render the client scorecard (F3/A12) instead of the retro")
    parser.add_argument("--campaigns", default=None,
                        help="comma-separated campaign keys for --scorecard")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    # Capture the REAL Job_Log before the dry run repoints JOB_LOG_PATH at a
    # scratch file, so "What the machine did" reads the same rows in a preview
    # as it does in the real run.
    job_log_path = os.environ.get("JOB_LOG_PATH") or str(tmp_dir() / "job_log.csv")
    if args.dry_run:
        # Evidence runs never write into the real Job_Log: the 48-hour shadow
        # watch reads that file. See shared.job_log.use_scratch_logs.
        job_log_mod.use_scratch_logs("retro_packet_dryrun")
    elif args.fixtures:
        # A replay is not this week's run either: its Job_Log row and anything
        # it might record in the shadow log go to scratch, never to the logs
        # the shadow watch and the Skool hand-off read.
        job_log_mod.use_scratch_logs("retro_packet_replay")

    if now is None:
        now = datetime.now(TZ)
        if args.as_of:
            from shared.slots import parse_iso, to_tz

            parsed = parse_iso(args.as_of)
            if parsed is None:
                parser.error("could not parse --as-of %r" % args.as_of)
            now = to_tz(parsed)

    fixtures = None
    if args.fixtures:
        try:
            fixtures = load_fixtures(args.fixtures_path)
        except (OSError, ValueError) as exc:
            parser.error("could not load fixtures: %s" % exc)

    if store is None:
        store = get_store()

    instantly, ghl = _clients(args.dry_run, offline=bool(fixtures))
    campaign_keys = [c.strip() for c in (args.campaigns or "").split(",") if c.strip()] or None
    if campaign_keys:
        # A typo here used to render a client-facing document full of zeros.
        try:
            scorecard_mod._campaign_ids(campaign_keys)
        except scorecard_mod.UnknownCampaign as exc:
            parser.error(str(exc))
    if campaign_keys and not args.scorecard:
        parser.error("--campaigns only means something with --scorecard")
    if args.dry_run and args.refresh and not args.pay:
        # --refresh is a request to pay again, and --dry-run does not pay.
        # Ignoring one of them silently is the worst of the three options.
        parser.error("--dry-run does not call the model, so --refresh would do nothing. "
                     "Add --pay to buy a fresh answer on a dry run, or use --now --refresh.")
    try:
        summary = run(
            now, instantly=instantly, ghl=ghl, store=store, dry_run=args.dry_run,
            weeks_back=args.weeks_back, fixtures=fixtures, complete=complete,
            refresh=args.refresh, skip_llm=args.no_llm, out_dir=args.out_dir,
            client=args.scorecard, campaign_keys=campaign_keys,
            pay=args.pay, force=args.force, job_log_path=job_log_path,
            replay=fixtures is not None,
        )
    except Exception as exc:  # noqa: BLE001 - a failed retro has to shout
        log_run(JOB, "failed", {"error": str(exc)[:400]})
        notify("Retro packet failed", "%s: %s" % (type(exc).__name__, str(exc)[:300]),
               priority="high", tags=["warning"])
        raise
    finally:
        for client_obj in (instantly, ghl):
            try:
                if client_obj is not None:
                    client_obj.close()
            except Exception:  # noqa: BLE001 - closing a client must not fail the run
                logger.warning("could not close %r", client_obj)

    details = dict((k, v) for k, v in summary.items() if k != "markdown")
    log_run(JOB, _status(summary), details)
    if summary.get("errors") and not args.dry_run and not summary.get("replay"):
        notify("Retro packet ran with missing sources",
               "; ".join(summary["errors"])[:400], priority="default", tags=["warning"])

    if args.json:
        print(json.dumps(details, indent=2, default=str))
    else:
        _print(summary)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "WARNING"))
    sys.exit(main())
