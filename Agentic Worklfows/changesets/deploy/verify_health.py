#!/usr/bin/env python3
"""Post-deploy check: GET <web URL>/health and compare it with what was meant.

    cd "/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows"
    python3 changesets/deploy/verify_health.py --expect-mode shadow --first-pass
    python3 changesets/deploy/verify_health.py --expect-mode shadow
    python3 changesets/deploy/verify_health.py --expect-mode live

The URL is read from .tmp/deploy/web_url.txt, which install_schedules.sh
--deploy writes from the deploy's own output (``--url`` overrides). This is
the only place the secret's MODE can be seen from outside: ``modal secret
list`` shows no values. It reads, it writes nothing.

Checks, each printed PASS or FAIL:
  * the real app answered (not the health-only fallback);
  * ``mode`` equals --expect-mode and ``live`` is true only for live;
  * ``base_url_set`` (skipped with --first-pass, when the URL is not known yet),
    and the BASE_URL host the last ``modal_secret.py --create`` for this mode
    wrote (.tmp/deploy/secret_history.jsonl) is the host of the URL checked
    here: /health only says yes or no, so a secret carrying another
    deployment's URL would pass on its own (and ``base_url_host`` from
    /health is compared too, if a later app version reports it);
  * ``webhook_secret`` and ``ghl_token`` are present;
  * ``approval_channels.any``: a card with working buttons can reach the phone;
  * ``templates.parity`` is "ok": the deployed template catalogue matches the
    reference hashes (a missing ``templates`` block fails too). "not_ready"
    (the app is still importing its modules) is polled again, within the same
    --attempts budget as a cold start; still not_ready after that fails.
    "mismatch", "reference_missing" and "error" fail at once.
Exit 0 only when every check passed. Each run appends its result (mode,
first pass or not, pass or fail; no URL path, no values) to
.tmp/deploy/health_history.jsonl: ``watch_clock.py start-report`` requires the
newest one to be a passing second-pass shadow check. Python 3.9.
"""
import argparse
import json
import sys
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    from changesets.deploy import common
except ImportError:  # run as a script
    import os

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from changesets.deploy import common


def fetch_health(url: str, timeout: float = 20.0) -> Dict[str, Any]:
    from urllib.request import Request, urlopen

    req = Request(url.rstrip("/") + "/health", headers={"Accept": "application/json"})
    with urlopen(req, timeout=timeout) as resp:  # noqa: S310 - https URL from our own deploy
        return json.loads(resp.read().decode("utf-8"))


def last_secret_host(expect_mode: str, path: Optional[str] = None) -> Optional[str]:
    """base_url_host of the newest successful secret create for this mode."""
    from changesets.deploy import modal_secret

    host = None
    try:
        with open(path or modal_secret.history_path(), "r", encoding="utf-8") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if rec.get("mode") == expect_mode and rec.get("status") == "created":
                    host = rec.get("base_url_host")
    except OSError:
        return None
    return host


PARITY_RETRYABLE = ("not_ready",)
RETRY_SECONDS = 5


def parity_not_ready(health: Dict[str, Any]) -> bool:
    """True when /health reports the template parity as not_ready: the app is
    still importing its modules, so a later poll can answer ok."""
    templates = health.get("templates") if isinstance(health, dict) else None
    return isinstance(templates, dict) and templates.get("parity") in PARITY_RETRYABLE


def template_parity_check(health: Dict[str, Any]) -> Tuple[str, bool, str]:
    """The cold-email template gate (CT3): the deployed catalogue must match the
    reference hashes. A missing block fails too (an app too old to report it).
    The detail names the parity status only, never ids or template text."""
    templates = health.get("templates")
    if not isinstance(templates, dict):
        return ("template parity is ok", False, "templates block missing")
    parity = templates.get("parity")
    return ("template parity is ok", parity == "ok", "parity=%r" % (parity,))


def evaluate(health: Dict[str, Any], expect_mode: str, first_pass: bool = False,
             url: Optional[str] = None, secret_host: Optional[str] = None) -> List[Tuple[str, bool, str]]:
    """[(check, passed, detail)] for one /health body."""
    live_expected = expect_mode == "live"
    channels = health.get("approval_channels") or {}
    checks = [
        ("real app answered", health.get("ok") is True and health.get("app") != "missing",
         "ok=%r app=%r detail=%r" % (health.get("ok"), health.get("app"), health.get("detail"))),
        ("mode is %s" % expect_mode, health.get("mode") == expect_mode, "mode=%r" % health.get("mode")),
        ("live is %s" % str(live_expected).lower(), health.get("live") is live_expected,
         "live=%r" % health.get("live")),
        ("webhook secret present", health.get("webhook_secret") is True,
         "webhook_secret=%r" % health.get("webhook_secret")),
        ("GHL token present", health.get("ghl_token") is True, "ghl_token=%r" % health.get("ghl_token")),
        ("a card with buttons can reach the phone", isinstance(channels, dict) and channels.get("any") is True,
         "approval_channels=%r" % channels),
        template_parity_check(health),
    ]
    if first_pass:
        checks.append(("BASE_URL (first pass: not known until this deploy printed the URL)", True,
                       "base_url_set=%r; re-create the secret with --base-url and redeploy" % health.get("base_url_set")))
    else:
        from urllib.parse import urlparse

        checks.append(("BASE_URL set", health.get("base_url_set") is True,
                       "base_url_set=%r" % health.get("base_url_set")))
        here = (urlparse(url or "").hostname or "").lower()
        reported = health.get("base_url_host")
        match = bool(here) and secret_host == here and (reported is None or str(reported).lower() == here)
        checks.append(("BASE_URL host is this deployment's (approval links point here)", match,
                       "checked URL host=%r, last secret create for %s wrote host=%r%s"
                       % (here, expect_mode, secret_host,
                          "" if reported is None else ", /health reports %r" % reported)))
    return checks


def record_result(expect_mode: str, first_pass: bool, url: str, passed: bool, failed: int = 0,
                  path: Optional[str] = None) -> None:
    """Append this check's outcome to .tmp/deploy/health_history.jsonl (best effort)."""
    import os
    from datetime import datetime, timezone
    from urllib.parse import urlparse

    record = {"ts_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
              "expect_mode": expect_mode, "first_pass": bool(first_pass), "passed": bool(passed),
              "failed_checks": int(failed), "url_host": (urlparse(url or "").hostname or "").lower() or None}
    try:
        with open(path or os.path.join(common.deploy_tmp(), "health_history.jsonl"), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, sort_keys=True) + "\n")
    except OSError as exc:
        sys.stderr.write("could not record the health result: %s\n" % exc)


def read_url(path: Optional[str] = None) -> Optional[str]:
    path = path or common.web_url_file()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            value = fh.read().strip()
    except OSError:
        return None
    return value or None


def main(argv: Optional[List[str]] = None, fetch: Callable[[str], Dict[str, Any]] = fetch_health,
         sleep: Callable[[float], None] = time.sleep) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--expect-mode", required=True, choices=("shadow", "live"))
    parser.add_argument("--first-pass", action="store_true",
                        help="the secret has no BASE_URL yet; do not fail on base_url_set")
    parser.add_argument("--url", help="the web URL (default: .tmp/deploy/web_url.txt)")
    parser.add_argument("--attempts", type=int, default=4, help="a fresh deploy can cold-start slowly")
    args = parser.parse_args(argv)

    url = args.url or read_url()
    if not url or not url.startswith("https://"):
        print("FAIL: no https web URL (pass --url, or deploy with install_schedules.sh --deploy)")
        return 1
    health = None
    last_error = None
    attempts = max(1, args.attempts)
    # One budget for both retries: a cold start that does not answer, and an
    # answer whose template parity is still not_ready. Any other parity status
    # is final and is judged below.
    for attempt in range(attempts):
        try:
            health = fetch(url)
        except Exception as exc:  # noqa: BLE001 - reported below
            last_error = "%s: %s" % (type(exc).__name__, exc)
            if attempt + 1 < attempts:
                sleep(RETRY_SECONDS)
            continue
        if parity_not_ready(health) and attempt + 1 < attempts:
            print("template parity is not_ready (the app is still loading); polling again (%d/%d)"
                  % (attempt + 1, attempts))
            sleep(RETRY_SECONDS)
            continue
        break
    if health is None:
        print("FAIL: %s/health did not answer (%s)" % (url, last_error))
        record_result(args.expect_mode, args.first_pass, url, False, 1)
        return 1
    failed = 0
    for name, passed, detail in evaluate(health, args.expect_mode, args.first_pass, url=url,
                                         secret_host=last_secret_host(args.expect_mode)):
        print("%s  %s  (%s)" % ("PASS" if passed else "FAIL", name, detail))
        failed += 0 if passed else 1
    record_result(args.expect_mode, args.first_pass, url, not failed, failed)
    if failed:
        print("\n%d check(s) FAILED. Do not start the watch or flip anything until they pass." % failed)
        return 1
    print("\nAll /health checks passed for %s in %s mode." % (url, args.expect_mode))
    return 0


if __name__ == "__main__":
    sys.exit(main())
