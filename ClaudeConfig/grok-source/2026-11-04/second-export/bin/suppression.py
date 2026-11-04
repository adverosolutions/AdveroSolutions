#!/usr/bin/env python3
"""do_not_reload suppression for Lead Gen (Lorenzo's rule, 2026-10-21).

Opt-outs and not-interested leads are held out for 3 months, then re-enter.
Source: ~/advero/state/reactivation/do_not_reload.csv (email, suppress_until[, added_ct, reason]).
READ ONLY. Never edit that file or anything in ~/advero/state/reactivation/.

An email is suppressed while today (America/Chicago) < suppress_until (YYYY-MM-DD).
On or after suppress_until it re-enters normally. Emails match lowercased and trimmed.
A row with a blank or unparseable suppress_until is treated as suppressed (safe side) and warned.
If the file is missing or unreadable: loud warning on stderr, suppression OFF, caller continues.

Override the path with env ADVERO_DO_NOT_RELOAD or the callers' --suppress-file (tests).

CLI (MillionVerifier queue build, or any CSV with an email column):
  suppression.py filter IN.csv OUT.csv [--email-col email] [--suppress-file F] [--today YYYY-MM-DD]
      writes OUT without suppressed rows, prints a JSON summary (suppressed count, emails).
  suppression.py list [--suppress-file F]    prints the currently active suppressed emails.
"""
import csv, json, os, sys
from datetime import date, datetime

DEFAULT_PATH = os.path.join(os.path.expanduser("~"), "advero/state/reactivation/do_not_reload.csv")


def today_ct():
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/Chicago")).date()
    except Exception:
        return date.today()  # box clock is America/Chicago


def norm(e):
    e = (e or "").strip().lower()
    return e[7:].strip() if e.startswith("mailto:") else e


def warn(msg):
    bar = "!" * 72
    print(f"{bar}\nWARNING (suppression): {msg}\n{bar}", file=sys.stderr)


def load(path=None, today=None):
    """Return dict(active=set of emails, status='on'|'off', path, total_rows, active_count,
    expired_count, bad_date_count, warning)."""
    path = path or os.environ.get("ADVERO_DO_NOT_RELOAD") or DEFAULT_PATH
    today = today or today_ct()
    info = dict(path=path, today=today.isoformat(), status="off", active=set(), total_rows=0,
                active_count=0, expired_count=0, bad_date_count=0, warning="")
    try:
        with open(path, newline="", encoding="utf-8-sig") as fh:
            r = csv.DictReader(fh)
            hdr = {(h or "").strip().lower(): h for h in (r.fieldnames or [])}
            if "email" not in hdr or "suppress_until" not in hdr:
                raise ValueError(f"missing email/suppress_until columns, got {r.fieldnames}")
            for row in r:
                em = norm(row.get(hdr["email"]))
                if not em:
                    continue
                info["total_rows"] += 1
                raw = (row.get(hdr["suppress_until"]) or "").strip()
                try:
                    until = date.fromisoformat(raw[:10])
                except ValueError:
                    info["bad_date_count"] += 1
                    info["active"].add(em)
                    continue
                if today < until:
                    info["active"].add(em)
                else:
                    info["expired_count"] += 1
    except Exception as ex:
        info["warning"] = f"do_not_reload file missing or unreadable ({path}): {ex}. SUPPRESSION IS OFF for this run."
        info["active"] = set()
        warn(info["warning"])
        return info
    if info["bad_date_count"]:
        warn(f"{info['bad_date_count']} do_not_reload row(s) have a bad suppress_until; treated as suppressed.")
    info["status"] = "on"
    info["active_count"] = len(info["active"])
    return info


def summary(info, suppressed, emails=None):
    """Summary block for callers' JSON output."""
    s = {"suppressed": suppressed, "suppression": info["status"],
         "suppression_file": info["path"], "suppression_active_emails": info["active_count"],
         "suppression_today_ct": info["today"]}
    if info["warning"]:
        s["suppression_warning"] = info["warning"]
    if emails is not None:
        s["suppressed_emails"] = sorted(emails)
    return s


def _arg(argv, name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


def main(argv):
    if len(argv) < 2 or argv[1] not in ("filter", "list"):
        sys.exit(__doc__)
    sf = _arg(argv, "--suppress-file")
    td = _arg(argv, "--today")
    info = load(sf, date.fromisoformat(td) if td else None)
    if argv[1] == "list":
        print(json.dumps(dict(summary(info, 0), emails=sorted(info["active"])), indent=2))
        return
    src, dst = argv[2], argv[3]
    col = _arg(argv, "--email-col", "email")
    with open(src, newline="", encoding="utf-8-sig") as fh:
        r = csv.DictReader(fh)
        fields = r.fieldnames or []
        if col not in fields:
            sys.exit(f"ERROR: no '{col}' column in {src}: {fields}")
        rows = list(r)
    keep, hit = [], []
    for row in rows:
        if norm(row.get(col)) in info["active"]:
            hit.append(norm(row.get(col)))
        else:
            keep.append(row)
    with open(dst, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader(); w.writerows(keep)
    print(json.dumps(dict(rows_in=len(rows), rows_out=len(keep), output=dst,
                          **summary(info, len(hit), hit)), indent=2))


if __name__ == "__main__":
    main(sys.argv)
