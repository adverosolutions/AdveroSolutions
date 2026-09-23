"""Change-set: the static "Interested-quiet" fallback subsequence per campaign.

The cadence service (services/reply_engine/cadence.py) is the real follow-up:
it inserts fresh calendar times every day. Instantly subsequences cannot do
that, so this change-set is only the fallback if the service is down: three
fixed emails landing on day 1, day 3 and day 7 with the booking link.

    python3 changesets/instantly_subsequences/apply_subsequences.py --dry-run
    python3 changesets/instantly_subsequences/apply_subsequences.py --apply --campaign cleaning_reactivation

There is exactly ONE copy source: changesets/instantly_phase0/subsequence_interested_quiet.json,
written by build_sequences.py and reviewed by Lorenzo. This script sends that
object verbatim (minus `_meta`); it holds no copy of its own, so the copy that
is approved is the copy that is created.

Enrolment is meant to be an explicit move, one lead per call
(shared.instantly.Instantly.move_leads_to_subsequence, `{"id", "subsequence_id"}`),
and only for a lead who was offered slots and did not answer: the D1 email opens
by saying those times are gone.

`conditions` is required by POST /subsequences and is sent with two empty lists
and no `reply_contains`, because an auto-condition on crm_status 1 would enrol
every Interested lead, including the positives who already hold a discovery
call, and email them that their slot is gone. HOW INSTANTLY EVALUATES AN EMPTY
CONDITION SET IS UNVERIFIED: no API document states it, and this change-set does
not claim it enrols nobody. runbooks/phase0.md go-live step 10 carries the
mandatory post-create check (read the new subsequence's enrolled-lead count,
delete it if it is not 0) that settles the question on the first campaign.

--dry-run lists the existing subsequences of every campaign (GET /subsequences,
read-only) and prints the full plan: conditions, schedule, the day each email
lands and the exact text of every email (--brief drops the text). That is the
approval surface; a plan that prints only a name approves nothing. --apply takes one campaign at a time,
needs MODE=live + ALLOW_LIVE_WRITES=1 and a typed confirmation, backs the
campaign's existing subsequence list up to backups/<ts>.json, then creates the
missing one through Instantly.subsequences_create (guard_write inside).
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

HERE = Path(__file__).resolve().parent
BASE_DIR = HERE.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from shared import settings  # noqa: E402
from shared.settings import LiveWriteBlocked, require_live  # noqa: E402
from changesets.instantly_phase0.phase0_lib import (  # noqa: E402
    SUBSEQUENCE_PATH,
    html_to_text,
    load_json,
    load_settings,
    validate_subsequence_copy,
)

# The shared change-set backup directory, the one runbooks/phase0.md names.
# It used to be HERE/"backups", one directory deeper, so anyone looking for the
# pre-create state where the runbook says it is found nothing.
BACKUP_DIR = BASE_DIR / "changesets" / "backups"
COPY_SOURCE = Path(SUBSEQUENCE_PATH)
BOOKING_URL = settings.BOOKING_URL

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_REFUSED = 2


def build_payloads(campaigns: Optional[Dict[str, Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    """One POST /subsequences body per campaign, read from the Phase 0 copy source.

    Nothing is composed here on purpose: a second copy of the wording is how the
    reviewed version and the sent version drift apart.
    """
    campaigns = campaigns if campaigns is not None else settings.CAMPAIGNS
    doc = load_json(str(COPY_SOURCE))
    staged = doc["campaigns"]
    cfg_all = load_settings()
    offers_md = settings.OFFERS_MD
    out = []
    for key in sorted(campaigns):
        if key not in staged:
            raise KeyError("%s has no Interested-quiet copy in %s; run build_sequences.py" % (key, COPY_SOURCE))
        payload = json.loads(json.dumps(staged[key]))  # deep copy
        expected_id = campaigns[key]["id"]
        if payload.get("parent_campaign") != expected_id:
            raise ValueError("%s: copy source targets %s but ids.json says %s" % (
                key, payload.get("parent_campaign"), expected_id))
        # Same money / period / guarantee gate the campaign sequences get. This
        # runs here and not only in pytest, so a --apply refuses on a copy edit
        # that never went through the suite. It goes to leads Instantly has
        # already marked interested, which is the worst audience for a promise
        # that is not in offers.md.
        rep = validate_subsequence_copy(key, payload, cfg_all, offers_md)
        if not rep.ok:
            raise ValueError("%s: Interested-quiet copy fails the offers.md gate:\n%s" % (key, rep.summary()))
        out.append(payload)
    return out


def strip_meta(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in payload.items() if not k.startswith("_")}


def send_days(payload: Dict[str, Any]) -> List[int]:
    """Cumulative day each email lands: pre_delay on step 1, then the gaps."""
    steps = (payload.get("sequences") or [{}])[0].get("steps") or []
    days = []
    day = 0
    for i, step in enumerate(steps):
        day += int(step.get("pre_delay") or 0) if i == 0 else int(steps[i - 1].get("delay") or 0)
        days.append(day)
    return days


def _existing(client: Any, parent_campaign: str, offline_ok: bool = False) -> List[Dict[str, Any]]:
    """Live subsequence list for a campaign.

    With no client this used to answer `[]`, which reads as "this campaign has
    no subsequences". On the apply path that empty list was written to the
    backup file as the pre-create state of a campaign whose real list had never
    been read. Only an explicitly offline plan may see the empty answer.
    """
    if client is None:
        if offline_ok:
            return []
        raise ValueError(
            "no Instantly client: the campaign's existing subsequences were never read, "
            "so there is nothing to back up or compare against")
    resp = client.subsequences_list(parent_campaign)
    if isinstance(resp, dict):
        return list(resp.get("items") or [])
    return list(resp or [])


def plan(client: Any, payloads: List[Dict[str, Any]], offline_ok: bool = True) -> List[Dict[str, Any]]:
    """Read-only: compare each payload against the campaign's live subsequences."""
    rows = []
    for payload in payloads:
        existing = _existing(client, payload["parent_campaign"], offline_ok=offline_ok)
        names = {str(e.get("name")) for e in existing}
        match = [e for e in existing if str(e.get("name")) == payload["name"]]
        rows.append({
            "campaign_key": (payload.get("_meta") or {}).get("campaign_key"),
            "meta": payload.get("_meta") or {},
            "parent_campaign": payload["parent_campaign"],
            "name": payload["name"],
            "existing_count": len(existing),
            "existing_names": sorted(names),
            "action": "exists" if match else "create",
            "existing_id": match[0].get("id") if match else None,
            "send_days": send_days(payload),
            "payload": strip_meta(payload),
        })
    return rows


def apply(client: Any, rows: List[Dict[str, Any]], backup_dir: Path = BACKUP_DIR) -> List[Dict[str, Any]]:
    """Live only, one campaign per call. Backs up that campaign's current
    subsequence list, then creates the missing one."""
    require_live("instantly", "subsequences_create")
    if client is None:
        raise ValueError("apply() needs a working Instantly client; there is nothing to write to "
                         "and nothing to back up")
    if len(rows) != 1:
        raise ValueError("apply() takes exactly one campaign per live run, got %d" % len(rows))
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = {r["parent_campaign"]: _existing(client, r["parent_campaign"]) for r in rows}
    with open(backup_dir / ("subsequences_before_%s.json" % stamp), "w", encoding="utf-8") as fh:
        json.dump(backup, fh, indent=2)
    results = []
    for r in rows:
        if r["action"] != "create":
            results.append(dict(r, result="skipped_exists"))
            continue
        res = client.subsequences_create(r["payload"])
        results.append(dict(r, result=res))
    return results


def enrolment_summary(conditions: Optional[Dict[str, Any]]) -> str:
    """The one line Lorenzo approves the live create from.

    It used to read only `conditions.crm_status`, so a subsequence carrying
    `lead_activity: [2]` (email opened) or a non-empty `reply_contains` printed
    "manual move only (conditions match no lead)" directly under the raw
    conditions JSON that contradicted it. Every field is reported, and even an
    all-empty set is reported as UNVERIFIED rather than as "matches nobody":
    no API document says how Instantly evaluates one.
    """
    c = conditions or {}
    crm = list(c.get("crm_status") or [])
    activity = list(c.get("lead_activity") or [])
    reply = c.get("reply_contains")
    triggers = []  # type: List[str]
    if crm:
        triggers.append("crm_status=%s" % crm)
    if activity:
        triggers.append("lead_activity=%s" % activity)
    if reply is not None:
        triggers.append("reply_contains=%r (an empty string is contained in EVERY reply)"
                        % reply if reply == "" else "reply_contains=%r" % reply)
    if triggers:
        return "AUTO-ENROLS by condition: " + "; ".join(triggers)
    return ("intended: manual move only. Conditions carry no trigger "
            "(crm_status=[], lead_activity=[], no reply_contains), but the semantics of an empty "
            "condition set are UNVERIFIED against a live create: read the new subsequence's "
            "enrolled-lead count straight after the create and delete it if it is not 0 "
            "(runbooks/phase0.md go-live step 10)")


def _print_plan(rows: List[Dict[str, Any]], bodies: bool = True, out: Callable[[str], None] = print) -> None:
    """The approval surface. It prints what actually fires: who gets enrolled,
    when each email lands, and (with --bodies) the words themselves."""
    out("%-26s %-8s %-46s existing" % ("campaign", "action", "name"))
    for r in rows:
        out("%-26s %-8s %-46s %d %s" % (
            r["campaign_key"], r["action"], r["name"][:46], r["existing_count"],
            ("(" + ", ".join(r["existing_names"]) + ")") if r["existing_names"] else ""))
    for r in rows:
        p = r["payload"]
        sched = (p.get("subsequence_schedule") or {}).get("schedules") or [{}]
        timing = sched[0].get("timing") or {}
        days = sched[0].get("days") or {}
        out("")
        out("--- %s (%s)" % (r["campaign_key"], r["action"]))
        out("    conditions:   %s" % json.dumps(p.get("conditions")))
        out("    enrolment:    %s" % enrolment_summary(p.get("conditions")))
        out("    move only if: %s" % ((r.get("meta") or {}).get("enrolment_precondition")
                                      or "UNSET (the D1 email says the times offered are gone)"))
        out("    schedule:     %s-%s %s days[%s]" % (
            timing.get("from"), timing.get("to"), sched[0].get("timezone"),
            "".join(d for d in sorted(days) if days[d])))
        out("    sends on day: %s" % r["send_days"])
        if bodies:
            for i, step in enumerate((p.get("sequences") or [{}])[0].get("steps") or []):
                text = html_to_text(step["variants"][0].get("body") or "")
                out("    --- email %d (day %d), subject %r" % (i + 1, r["send_days"][i], step["variants"][0].get("subject")))
                for line in text.split("\n"):
                    out("        %s" % line)
    creates = [r for r in rows if r["action"] == "create"]
    out("")
    out("plan: %d to create, %d already exist" % (len(creates), len(rows) - len(creates)))


def main(argv: Optional[List[str]] = None, client: Any = None,
         out: Callable[[str], None] = print, confirm: Optional[Callable[[str], str]] = None) -> int:
    p = argparse.ArgumentParser(prog="apply_subsequences", description=__doc__.split("\n\n")[0])
    g = p.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", help="read-only diff against live (default)")
    g.add_argument("--apply", action="store_true",
                   help="create the missing subsequence for ONE campaign (MODE=live + ALLOW_LIVE_WRITES=1 only)")
    p.add_argument("--campaign", help="campaign key from config/ids.json (required with --apply)")
    p.add_argument("--offline", action="store_true", help="do not call Instantly at all (plan against an empty list)")
    p.add_argument("--brief", action="store_true", help="drop the email text from the plan (it is printed by default)")
    p.add_argument("--json", action="store_true", help="print the plan as JSON")
    p.add_argument("--yes", action="store_true", help="skip the interactive confirmation on --apply")
    args = p.parse_args(argv)

    if args.apply and args.offline:
        out("REFUSED: --apply cannot run with --offline; there is nothing to write to.")
        return EXIT_REFUSED
    if args.apply and not args.campaign:
        out("REFUSED: --apply needs --campaign <key>; live application is one campaign at a time.")
        return EXIT_REFUSED
    if args.campaign and args.campaign not in settings.CAMPAIGNS:
        out("unknown campaign key %r; known: %s" % (args.campaign, sorted(settings.CAMPAIGNS)))
        return EXIT_INVALID

    payloads = build_payloads()
    if args.campaign:
        payloads = [p_ for p_ in payloads if (p_.get("_meta") or {}).get("campaign_key") == args.campaign]

    if client is None and not args.offline:
        try:
            from shared.instantly import default_client
            client = default_client()
        except Exception as exc:  # noqa: BLE001 - no key: plan offline
            out("Instantly client unavailable (%s); planning offline" % exc)
            client = None

    if args.apply and client is None:
        out("REFUSED: --apply needs a working Instantly client. Without one the campaign's existing "
            "subsequences are never read, so the backup would record an empty list for a campaign "
            "whose real state is unknown. Fix INSTANTLY_API_KEY and re-run.")
        return EXIT_REFUSED

    rows = plan(client, payloads, offline_ok=not args.apply)
    if args.json:
        out(json.dumps(rows, indent=2, default=str))
    else:
        _print_plan(rows, bodies=not args.brief, out=out)

    if args.apply:
        if not args.yes:
            prompt = confirm or input
            answer = prompt("Type the campaign key (%s) to confirm the LIVE create: " % args.campaign)
            if answer.strip() != args.campaign:
                out("aborted: confirmation did not match")
                return EXIT_REFUSED
        try:
            results = apply(client, rows)
        except LiveWriteBlocked as exc:
            out("REFUSED: %s" % exc)
            return EXIT_REFUSED
        for r in results:
            out("%-26s %s" % (r["campaign_key"], json.dumps(r.get("result"), default=str)[:160]))
        return EXIT_OK
    out("dry-run only; nothing was created. mode=%s" % os.environ.get("MODE", "shadow"))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
