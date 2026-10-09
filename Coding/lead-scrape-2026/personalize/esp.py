"""MX-based mailbox provider lookup with an on-disk cache (output/mx_cache.json).
esp_of("a@b.com") -> "google" | "microsoft" | "yahoo" | "zoho" | "other" | "none"
"""
import json, os, re, subprocess, threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

CACHE = Path(__file__).resolve().parents[1] / "output" / "mx_cache.json"
_lock = threading.Lock()
_cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}

def _classify(mx_hosts):
    h = " ".join(mx_hosts).lower()
    if not h: return "none"
    if "google.com" in h or "googlemail.com" in h: return "google"
    if "outlook.com" in h or "office365" in h or "microsoft" in h or "hotmail.com" in h: return "microsoft"
    if "yahoodns" in h or "yahoo.com" in h: return "yahoo"
    if "zoho" in h: return "zoho"
    return "other"

def _mx(domain):
    try:
        out = subprocess.run(["dig", "+short", "+time=3", "+tries=1", "MX", domain], capture_output=True, text=True, timeout=8).stdout
        hosts = [l.split()[-1] for l in out.splitlines() if l.strip() and l.split()[0].isdigit()]
        return hosts
    except Exception:
        return []

def esp_of(email):
    d = (email or "").split("@")[-1].strip().lower()
    if not d: return "none"
    with _lock:
        if d in _cache: return _cache[d]
    v = _classify(_mx(d))
    with _lock:
        _cache[d] = v
    return v

def prime(emails, workers=32):
    doms = sorted({(e or "").split("@")[-1].strip().lower() for e in emails if e and "@" in e} - set(_cache))
    with ThreadPoolExecutor(workers) as ex:
        list(ex.map(lambda d: esp_of("x@" + d), doms))
    save()
    return len(doms)

def save():
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        CACHE.write_text(json.dumps(_cache, indent=0, sort_keys=True))
