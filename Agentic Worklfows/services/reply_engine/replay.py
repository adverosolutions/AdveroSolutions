"""Replay recorded replies through the full pipeline in shadow.

    python3 -m services.reply_engine.replay --fixture services/reply_engine/tests/fixtures/instantly_replies_2026-09.json

Writes .tmp/shadow_replay_<date>.jsonl (one line per reply: classification,
actions, draft when one was produced) and prints a summary table. MODE is
forced to shadow, notifications off, LLM faked unless --real-llm.
"""
import argparse
import collections
import json
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from shared import slots

logger = logging.getLogger("reply_engine.replay")


def _load(path: Path) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    return data if isinstance(data, list) else data.get("items", [])


def _leads_by_email(fixture_path: Path) -> Dict[str, Dict[str, Any]]:
    candidate = fixture_path.parent / "instantly_replied_leads_2026-09.json"
    out = {}  # type: Dict[str, Dict[str, Any]]
    if candidate.exists():
        for lead in _load(candidate):
            em = (lead.get("email") or "").lower()
            if em:
                out[em] = lead
    return out


def replay(fixture_path: Path, out_path: Path, store, ghl=None, instantly=None, offset_minutes: int = 2) -> Dict[str, Any]:
    from services.reply_engine import app as app_mod
    from services.reply_engine.draft import busy_blocks_from_ids
    from services.reply_engine.models import ReplyEvent

    deps = app_mod.configure(store=store, ghl=ghl, instantly=instantly)
    items = sorted(_load(fixture_path), key=lambda it: str(it.get("timestamp_created") or ""))
    leads = _leads_by_email(fixture_path)
    labels = collections.Counter()  # type: collections.Counter
    methods = collections.Counter()  # type: collections.Counter
    would_do = collections.Counter()  # type: collections.Counter
    drafted = blocklisted = llm_calls = 0
    booked = []  # type: List[Dict[str, Any]]
    choices = []  # type: List[Dict[str, Any]]
    lines = []  # type: List[Dict[str, Any]]
    from shared import llm as llm_mod

    counter = {"n": 0}
    real_fakes = dict(llm_mod._FAKES)  # noqa: SLF001 - count calls through the fake registry

    def counting(role):
        inner = real_fakes.get(role)

        def fn(system, user, json_mode):
            counter["n"] += 1
            if inner is not None:
                return inner(system, user, json_mode)
            return llm_mod._fake_response(role, system, user, json_mode)  # noqa: SLF001

        return fn

    if llm_mod.is_fake():
        for role in ("classify", "escalate", "draft"):
            llm_mod.register_fake(role, counting(role))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        for item in items:
            email = (item.get("lead") or item.get("from_address_email") or "").lower()
            event = ReplyEvent.from_poller_item(item, lead=leads.get(email), source="replay")
            now = event.received_at + timedelta(minutes=offset_minutes)
            before = counter["n"]
            # per lead, so a block that IS this lead's own call does not make
            # the engine counter-propose around the appointment they wrote about
            blocks = busy_blocks_from_ids(exclude_email=event.lead_email)
            res = app_mod.process_event(event, deps=deps, now=now, busy_blocks=blocks)
            calls = counter["n"] - before
            llm_calls += calls
            label = res.get("label")
            labels[label] += 1
            methods[res.get("method")] += 1
            for a in res.get("actions", []):
                would_do["%s.%s" % (a["system"], a["action"])] += 1
                if a["action"] == "blocklist_create":
                    blocklisted += 1
            if res.get("draft"):
                drafted += 1
            if res.get("booking"):
                booked.append({"lead": event.lead_email, "slot": res["booking"]["slot"], "shadow": res["booking"].get("shadow")})
            if res.get("requested_time"):
                choices.append(dict(res["requested_time"], lead=event.lead_email,
                                    countered=(res.get("draft") or {}).get("offered_slots")))
            line = {
                "email_id": event.email_id, "lead": event.lead_email, "campaign_key": event.campaign_key, "received_at": event.received_at.isoformat(),
                "subject": event.subject, "classification": {"label": label, "confidence": res.get("confidence"), "method": res.get("method"),
                                                             "reason": res.get("reason"), "extracted": res.get("extracted")},
                "llm_calls": calls,
                "actions": [{"system": a["system"], "action": a["action"], "kind": a["kind"], "payload": a["payload"]} for a in res.get("actions", [])],
                "draft": ({"subject": res["draft"]["subject"], "body_text": res["draft"]["body_text"], "offered_slots": res["draft"]["offered_slots"],
                           "problems": res["draft"]["problems"], "model": res["draft"]["model"]} if res.get("draft") else None),
                "approval_token": res.get("approval_token"), "status": res.get("status"),
                "booking": res.get("booking"), "requested_time": res.get("requested_time"),
                "cadence_stopped": res.get("cadence_stopped"), "hooks": res.get("hooks"),
            }
            lines.append(line)
            fh.write(json.dumps(line, default=str, ensure_ascii=False) + "\n")

    if llm_mod.is_fake():
        llm_mod.clear_fakes()
        for role, fn in real_fakes.items():
            llm_mod.register_fake(role, fn)

    return {"replies": len(items), "labels": dict(labels), "methods": dict(methods), "would_do": dict(would_do), "drafted": drafted,
            "blocklisted": blocklisted, "llm_calls": llm_calls, "booked": booked, "choices": choices,
            "out": str(out_path), "lines": lines}


def print_summary(summary: Dict[str, Any]) -> None:
    print("Replay: %d replies -> %s" % (summary["replies"], summary["out"]))
    print("\nLabel counts")
    for label, n in sorted(summary["labels"].items(), key=lambda kv: (-kv[1], kv[0])):
        print("  %-24s %3d" % (label, n))
    print("\nClassification method: %s" % ", ".join("%s=%d" % kv for kv in sorted(summary["methods"].items())))
    print("LLM calls (fake): %d" % summary["llm_calls"])
    print("Positives/questions drafted: %d" % summary["drafted"])
    print("Blocklisted (would_do): %d" % summary["blocklisted"])
    print("Calls booked (would_do): %d" % len(summary.get("booked", [])))
    for b in summary.get("booked", []):
        print("  %-38s %s" % (b["lead"][:38], b["slot"]))
    if summary.get("choices"):
        print("Waiting on Lorenzo (asked for a time outside the slot rule): %d" % len(summary["choices"]))
        for c in summary["choices"]:
            print("  %-38s asked %s (%s), countered %s" % (c["lead"][:38], c["slot"], c["status"], ", ".join(c.get("countered") or [])))
    print("\nwould_do records by system.action")
    for key, n in sorted(summary["would_do"].items()):
        print("  %-36s %3d" % (key, n))
    print("\nPer reply")
    print("%-19s %-34s %-22s %-5s %s" % ("received", "lead", "label", "draft", "slots"))
    for ln in summary["lines"]:
        d = ln.get("draft") or {}
        print("%-19s %-34s %-22s %-5s %s" % (ln["received_at"][:19], ln["lead"][:34], (ln["classification"]["label"] or "")[:22],
                                             "yes" if d else "", ", ".join(d.get("offered_slots", []))))


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Replay recorded replies in shadow")
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--out", default=None, help="output JSONL (default .tmp/shadow_replay_<date>.jsonl)")
    parser.add_argument("--date", default=None, help="date label for the output file (default: today)")
    parser.add_argument("--real-llm", action="store_true", help="use the real Claude models (costs tokens)")
    parser.add_argument("--show-drafts", action="store_true")
    args = parser.parse_args(argv)

    os.environ["MODE"] = "shadow"
    os.environ.pop("ALLOW_LIVE_WRITES", None)
    os.environ.setdefault("NOTIFY", "off")
    # The replay is evidence, not operation: its rows must not be mixed into
    # the job log the 48-hour shadow watch is read from (the --out JSONL is the
    # replay's own record). See shared.job_log.use_scratch_logs.
    from shared.job_log import use_scratch_logs

    use_scratch_logs("replay")
    if not args.real_llm:
        os.environ["LLM_FAKE"] = "1"

    from shared.paths import tmp_file
    from shared.store import JsonFileStore
    from shared.ghl import GHL
    from shared.instantly import Instantly, default_client
    from shared import llm as llm_mod
    from services.reply_engine.classify import install_offline_fakes

    # llm_mod.is_fake(), not LLM_FAKE == "1": a replay started with
    # LLM_FAKE=true skipped the keyword stand-ins and shared.llm's generic
    # default answered positive_interested 0.95 to all 44 replies, which reads
    # exactly like a real Haiku run.
    if llm_mod.is_fake():
        install_offline_fakes()
    fixture = Path(args.fixture)
    if not fixture.is_absolute():
        from shared.paths import BASE_DIR

        fixture = (BASE_DIR / fixture) if not fixture.exists() else fixture
    date_label = args.date or datetime.now(slots.TZ).date().isoformat()
    out_path = Path(args.out) if args.out else tmp_file("shadow_replay_%s.jsonl" % date_label)
    store = JsonFileStore(tmp_file("replay_store.json"))
    store.clear()
    try:
        instantly = default_client()
    except Exception:  # noqa: BLE001 - no key: shadow writes never need one
        instantly = Instantly(api_key="replay-no-key")
    summary = replay(fixture, out_path, store, ghl=GHL(), instantly=instantly)
    print_summary(summary)
    if args.show_drafts:
        for ln in summary["lines"]:
            if ln.get("draft"):
                print("\n=== %s (%s)\nSubject: %s\n%s" % (ln["lead"], ln["classification"]["label"], ln["draft"]["subject"], ln["draft"]["body_text"]))
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "WARNING"))
    sys.exit(main())
