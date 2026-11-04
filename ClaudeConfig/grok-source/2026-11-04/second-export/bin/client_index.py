#!/usr/bin/env python3
"""Shared client/lead index check for Lead Gen (Lorenzo's cross-referencing rule, 2026-10-21).

Reads ~/advero/state/clients/INDEX.csv (READ ONLY here; columns key,company,domain,emails,...).
A pulled row whose email, or whose domain, already has a client file is SKIPPED from bulk pulls
(counted as `client_known`), so no bot re-prospects a company another bot is already handling.
Missing/unreadable index: warning on stderr, check off, caller continues.
Override path with env ADVERO_CLIENT_INDEX (tests).
"""
import csv, os, sys

DEFAULT = os.path.join(os.path.expanduser("~"), "advero/state/clients/INDEX.csv")


def _dom(d):
    d = (d or "").strip().lower()
    for p in ("https://", "http://"):
        if d.startswith(p): d = d[len(p):]
    d = d.split("/")[0]
    return d[4:] if d.startswith("www.") else d


def load(path=None):
    path = path or os.environ.get("ADVERO_CLIENT_INDEX") or DEFAULT
    info = dict(path=path, status="off", emails=set(), domains=set(), files={})
    try:
        with open(path, newline="", encoding="utf-8-sig") as fh:
            for r in csv.DictReader(fh):
                f = (r.get("file") or r.get("key") or "").strip()
                d = _dom(r.get("domain"))
                if d:
                    info["domains"].add(d); info["files"][d] = f
                for e in (r.get("emails") or "").replace(",", ";").split(";"):
                    e = e.strip().lower()
                    if e:
                        info["emails"].add(e); info["files"][e] = f
        info["status"] = "on"
    except Exception as ex:
        print(f"WARNING (client_index): cannot read {path}: {ex}; client check OFF", file=sys.stderr)
    return info


def match(info, email="", domain=""):
    """Return the client file key if email or domain is known, else ''."""
    e = (email or "").strip().lower(); d = _dom(domain)
    if e and e in info["emails"]: return info["files"].get(e) or e
    ed = e.split("@")[1] if "@" in e else ""
    for k in (d, ed):
        if k and k in info["domains"]: return info["files"].get(k) or k
    return ""


def summary(info, hits):
    return {"client_index": info["status"], "client_known": len(hits), "client_known_hits": hits[:50]}
