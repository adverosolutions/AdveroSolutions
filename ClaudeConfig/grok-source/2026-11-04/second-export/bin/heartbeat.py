#!/usr/bin/env python3
"""Routine heartbeat (audit fix 2026-10-22).

Every routine's FIRST step:   python3 ~/advero/bin/heartbeat.py beat <name> [note]
COO hourly check:             python3 ~/advero/bin/heartbeat.py check
  prints JSON {"missed": [...], "not_enrolled": [...]}; exit 1 if anything missed.
Names and slots live in ~/advero/state/org/routine_expected.json.
A routine is only checked after its first beat ever, so new entries never false-alarm.
Missed slots are looked at for today and yesterday only. Internal files only.
"""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

CT = ZoneInfo("America/Chicago")
LOG = Path.home() / "advero/state/heartbeats.jsonl"
EXP = Path.home() / "advero/state/org/routine_expected.json"


def beats():
    out = {}
    if LOG.exists():
        for line in LOG.read_text().splitlines():
            try:
                o = json.loads(line)
                out.setdefault(o["name"], []).append(datetime.fromisoformat(o["at_ct"]))
            except Exception:
                pass
    return out


def slots(r, now):
    res = []
    for back in (1, 0):
        day = (now - timedelta(days=back)).date()
        if day.weekday() not in r["days"]:
            continue
        for t in r["times"]:
            if t.startswith("every:"):
                continue  # interval routines: checked by gap below
            h, m = map(int, t.split(":"))
            res.append(datetime(day.year, day.month, day.day, h, m, tzinfo=CT))
    return res


def check():
    now = datetime.now(CT)
    exp = json.loads(EXP.read_text())["routines"]
    b = beats()
    missed, not_enrolled = [], []
    for r in exp:
        got = sorted(b.get(r["name"], []))
        if not got:
            not_enrolled.append(r["name"])
            continue
        g = timedelta(minutes=r.get("grace_min", 20))
        for t in r["times"]:
            if t.startswith("every:"):
                every = timedelta(minutes=int(t.split(":")[1]))
                if now.weekday() in r["days"] and now - got[-1] > every + g:
                    missed.append({"name": r["name"], "owner": r["owner"], "last_beat_ct": got[-1].isoformat(timespec="minutes"), "why": "interval gap"})
        first = got[0]
        for s in slots(r, now):
            if s < first or s + g > now:
                continue
            if not any(s - timedelta(minutes=60) <= x <= s + g for x in got):
                missed.append({"name": r["name"], "owner": r["owner"], "slot_ct": s.isoformat(timespec="minutes")})
    print(json.dumps({"checked_ct": now.isoformat(timespec="minutes"), "missed": missed, "not_enrolled": not_enrolled}, indent=2))
    return 1 if missed else 0


def main(a):
    if len(a) >= 2 and a[0] == "beat":
        rec = {"name": a[1], "at_ct": datetime.now(CT).isoformat(timespec="seconds"), "note": " ".join(a[2:])}
        with LOG.open("a") as fh:
            fh.write(json.dumps(rec) + "\n")
        print(json.dumps(rec))
        return 0
    if a and a[0] == "check":
        return check()
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
