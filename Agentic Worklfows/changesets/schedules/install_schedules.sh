#!/usr/bin/env bash
#
# Deploy the Modal half of the schedule. DOCUMENTED AND NOT RUN.
#
# Nothing in this repo has executed this script and nothing should until
# Lorenzo has read runbooks/deployment.md and said yes. It is here so that
# the going-live step is a reviewed file rather than a command somebody
# reconstructs from memory at 07:00 on a bad morning.
#
# What it does
# ------------
# `modal deploy` registers the Modal schedules of the tiers in DEPLOY_TIERS
# (default: sales only, owner decision R3) plus the web endpoint, all at once.
# The app is the unit: a deploy replaces the whole app, so DEPLOY_TIERS must
# list every tier to keep (sales,marketing, not marketing). Laptop schedules
# (owner decision R4) are never deployed here; they are staged in
# changesets/schedules/laptop/.
#
# It does NOT choose shadow or live. The deployed app reads MODE and
# ALLOW_LIVE_WRITES from the Modal secret, which only
# changesets/deploy/modal_secret.py writes. (The laptop's own live switches,
# LAPTOP_LIVE_TIERS and LAPTOP_PAID_JOBS, are read by laptop_runner.py from
# the saved .env only; nothing here touches them.) The EXPECTED mode is the second
# argument, and the post-deploy check reads /health and fails when the
# deployment reports anything else.
#
# Nothing technical stops this script from running: the PreToolUse hook only
# matches command text. The DEPLOY answer is read from the terminal
# (/dev/tty), not stdin, so it cannot be piped in; with no terminal the deploy
# refuses. What protects the live systems is the secret's MODE
# (shared.settings.guard_write). Run it from your own terminal.
#
# The first shadow deploy (--first-pass) records the HAND-OFF START
# (.tmp/deploy/handoff_start.txt) just before `modal deploy`, through
# changesets/deploy/watch_clock.py begin: at or before the first reply the
# shadow poller can see, kept by a retried first pass, fresh only with
# --new-watch. The REPORT START is a separate file, set later by hand
# (watch_clock.py start-report), once the app is up and settled.
#
# The live flip (--deploy live) runs NO preflight: the preflight must already
# have passed on this code (changesets/deploy/preflight_stamp.py, written by
# --preflight). It checks that stamp, asks DEPLOY, creates the live secret
# (modal_secret.py asks CREATE) and deploys right after it: nothing slow or
# fallible sits between the secret and the deploy, and any failure once the
# secret may be live prints the abort sequence.
#
# Usage, when the time comes
# --------------------------
#   cd "/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows"
#   bash changesets/schedules/install_schedules.sh --preflight
#   DEPLOY_TIERS=sales bash changesets/schedules/install_schedules.sh --deploy shadow --first-pass [--new-watch]
#   DEPLOY_TIERS=sales bash changesets/schedules/install_schedules.sh --deploy shadow
#   DEPLOY_TIERS=sales bash changesets/schedules/install_schedules.sh --preflight      # right before the flip
#   DEPLOY_TIERS=sales bash changesets/schedules/install_schedules.sh --deploy live    # creates the live secret too
#
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$BASE_DIR"

MODE_ARG="${1:---preflight}"
EXPECT_MODE="${2:-}"
FIRST_PASS=""
NEW_WATCH=""
if [ "$#" -gt 2 ]; then
  for extra in "${@:3}"; do
    case "$extra" in
      --first-pass) FIRST_PASS="--first-pass" ;;
      --new-watch)  NEW_WATCH="--new-watch" ;;
      *) echo "unknown option: $extra (only --first-pass and --new-watch)" >&2; exit 2 ;;
    esac
  done
fi
DEPLOY_DIR=".tmp/deploy"
# live flip state, read by the EXIT trap: none | maybe | created | create_failed
LIVE_SECRET_STATE="none"

summary() {
  python3 - <<'PY'
import json, sys
sys.path.insert(0, ".")
from services.reply_engine import modal_app
print(json.dumps(modal_app.deploy_summary(), indent=2))
PY
}

preflight() {
  echo "== 1. the schedule data and the staged laptop files match modal_app, and the split is valid =="
  python3 changesets/schedules/build_schedules.py --check

  echo
  echo "== 2. the app imports, and exactly the deployed schedules are Modal functions =="
  python3 - <<'PY'
import sys
sys.path.insert(0, ".")
from services.reply_engine import modal_app
import modal

bad = []
for name in modal_app.SCHEDULED_FUNCTIONS:
    # NOT callable(): a decorated @app.function is a modal.Function object and
    # modal.Function is not callable in modal 1.2.x.
    fn = getattr(modal_app, name, None)
    if not isinstance(fn, modal.Function):
        bad.append("%s has no modal function (got %r)" % (name, type(fn).__name__))
registered = set(modal_app.app.registered_functions)
expected = set(modal_app.SCHEDULED_FUNCTIONS) | {"web"}
if registered != expected:
    bad.append("the app registers %s, expected %s" % (sorted(registered), sorted(expected)))
if bad:
    raise SystemExit("REFUSING: " + "; ".join(bad))
print("tiers %s: %d schedules registered, plus web" % (",".join(modal_app.DEPLOY_TIERS),
                                                      len(modal_app.SCHEDULED_FUNCTIONS)))
PY

  echo
  echo "== 3. every deployed module imports from a copy of exactly the Modal mounts =="
  python3 changesets/schedules/build_schedules.py --check-image

  echo
  echo "== 4. the secret list covers every key the deployed code reads =="
  python3 -m pytest shared/tests/test_settings.py::test_every_env_key_is_deployable -q

  echo
  echo "== 5. the whole suite is green =="
  python3 -m pytest -q

  echo
  echo "== 6. NOT CHECKED HERE (manual; this script cannot see them) =="
  echo "   a. The secret's MODE. \`modal secret list\` shows no values, so nothing here can read it."
  echo "      The only evidence is the post-deploy /health check (--deploy runs it) and"
  echo "      \`python3 changesets/deploy/modal_secret.py --mode shadow\`, which prints what WOULD be written."
  echo "   b. The Modal plan quota. This deploy registers the numbers below; confirm the"
  echo "      adverosolutionsbackup workspace plan allows that many crons and web endpoints"
  echo "      (modal.com -> Settings -> Plan) before deploying:"
  summary

  echo
  echo "== 7. the cold-email template catalogue hashes are rebuilt and match =="
  # --write refreshes config/template_catalogue_hashes.json (the reference the
  # deployed app compares against); --check recomputes and exits 1 on any
  # difference. It never writes approved_templates.json. The first --write
  # creates the reference as a new, untracked file; once it is committed,
  # every preflight leaves it changed in git (at least its generated_at
  # line): review and commit it with the code it was built from.
  if ! python3 changesets/deploy/template_parity.py --write; then
    echo "REFUSING: template_parity.py --write failed. Not deployed." >&2
    exit 1
  fi
  if ! python3 changesets/deploy/template_parity.py --check; then
    echo "REFUSING: template_parity.py --check found a mismatch. Not deployed." >&2
    exit 1
  fi

  echo
  echo "== 8. ladder templates that cannot auto-send (cadence, show-rate, no-show) =="
  # Once the CT3 send paths are deployed, a ladder message whose template is
  # not approved at its current text, or could not be rendered, is held
  # instead of sent; so is every ladder message while the kill switch is on.
  local report line1 line2 line3 rest unapproved unextractable killswitch
  if ! report="$(python3 changesets/deploy/template_parity.py --report-unapproved)"; then
    echo "REFUSING: template_parity.py --report-unapproved failed. Not deployed." >&2
    exit 1
  fi
  # The three header lines, no pipe (pipefail + SIGPIPE).
  line1="${report%%$'\n'*}"; rest="${report#*$'\n'}"
  line2="${rest%%$'\n'*}"; rest="${rest#*$'\n'}"
  line3="${rest%%$'\n'*}"
  case "$line1" in "UNAPPROVED LADDER IDS: "*) unapproved="${line1#UNAPPROVED LADDER IDS: }" ;; *) unapproved="" ;; esac
  case "$line2" in "UNEXTRACTABLE LADDER IDS: "*) unextractable="${line2#UNEXTRACTABLE LADDER IDS: }" ;; *) unextractable="" ;; esac
  case "$line3" in "KILL SWITCH: "*) killswitch="${line3#KILL SWITCH: }" ;; *) killswitch="" ;; esac
  case "$unapproved" in ''|*[!0-9]*)
    echo "REFUSING: could not read the unapproved count (got: $line1). Not deployed." >&2; exit 1 ;;
  esac
  case "$unextractable" in ''|*[!0-9]*)
    echo "REFUSING: could not read the unextractable count (got: $line2). Not deployed." >&2; exit 1 ;;
  esac
  case "$killswitch" in on|off) ;; *)
    echo "REFUSING: could not read the kill switch state (got: $line3). Not deployed." >&2; exit 1 ;;
  esac
  printf '%s\n' "$report"
  if [ "$killswitch" != "off" ]; then
    echo
    echo "WARNING: the template kill switch is ON (AUTO_SEND_TEMPLATES in this shell, or \"auto_send\" in"
    echo "config/approved_templates.json). Deployed like this, every cadence, show-rate and no-show message"
    echo "is held, approved or not, and every reply becomes a card. The Modal secret has its own"
    echo "AUTO_SEND_TEMPLATES value, which this laptop cannot read."
  fi
  # Anything but a clean "0 and 0" asks for HOLD: fails closed on a surprise.
  if [ "$unapproved" != "0" ] || [ "$unextractable" != "0" ]; then
    echo
    echo "${unapproved} ladder template(s) are not approved at their current text and ${unextractable} could not be rendered."
    echo "Deployed like this, every message that uses one is held, not sent, until it is approved (or the code"
    echo "is fixed). A show-rate or no-show message whose send time passes while held is dropped, not sent late."
    # Like the DEPLOY answer: read from the terminal, never from a pipe. With
    # no interactive terminal, stop.
    if [ ! -t 0 ] || ! { : < /dev/tty; } 2>/dev/null; then
      echo "No interactive terminal to read the HOLD answer from. Not deployed." >&2
      exit 1
    fi
    local hold=""
    IFS= read -r -p "Continue with these held? [type HOLD] " hold < /dev/tty
    if [ "$hold" != "HOLD" ]; then
      echo "Not deployed. Approve the templates above (or fix the code), or run again and type HOLD." >&2
      exit 1
    fi
    echo "HOLD accepted: ${unapproved} unapproved and ${unextractable} unrendered ladder template(s) stay held."
  fi

  echo
  # The stamp the live flip needs. Only here, and only after checks 1-5, 7
  # and 8 passed (set -e stops at the first failure); preflight_stamp.py has
  # no command that writes one.
  python3 - <<'PY'
import sys
sys.path.insert(0, ".")
from changesets.deploy import preflight_stamp
rec = preflight_stamp._write_after_preflight()
print("preflight stamp written: %s (%d files, tiers %s)" % (rec["ts_utc"], rec["files"], ",".join(rec["deploy_tiers"])))
PY
  echo "Preflight: the automated checks 1 to 5, 7 and 8 passed. The two manual items in 6 were NOT checked."
  echo "Nothing was deployed. The live flip (--deploy live) accepts this preflight for 60 minutes, on this code only."
}

abort_text() {
  cat <<'ABORT' >&2

======================= THE LIVE SECRET MAY BE IN PLACE =======================
The live flip did not finish. Any new container of the running app may be
reading MODE=live. Abort NOW, in this order (runbooks/deployment.md step 5,
"If the live deploy fails"):

  python3 -m modal app stop advero-reply-engine
  python3 changesets/deploy/modal_secret.py --mode shadow --base-url "$(cat .tmp/deploy/web_url.txt)" --create
  python3 changesets/deploy/watch_report.py --store-mode live --min-hours 0 --skip-laptop
  DEPLOY_TIERS=sales bash changesets/schedules/install_schedules.sh --deploy shadow
===============================================================================
ABORT
}

on_exit() {
  local code=$?
  if [ "$code" -ne 0 ] && [ "$LIVE_SECRET_STATE" != "none" ]; then
    abort_text
  fi
  return $code
}
trap on_exit EXIT

secret_outcome_since() {
  # created | create_failed | none: the newest live secret create recorded at or after $1
  python3 - "$1" <<'PY'
import json, sys
sys.path.insert(0, ".")
from changesets.deploy import modal_secret
since = sys.argv[1]
status = "none"
try:
    with open(modal_secret.history_path(), "r", encoding="utf-8") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get("mode") == "live" and str(rec.get("ts_utc", "")) >= since:
                status = rec.get("status") or "create_failed"
except OSError:
    pass
print(status)
PY
}

deploy() {
  case "$EXPECT_MODE" in
    shadow|live) ;;
    *) echo "usage: $0 --deploy shadow|live [--first-pass] [--new-watch]   (the mode the secret is expected to hold)" >&2; exit 2 ;;
  esac
  if [ "$EXPECT_MODE" = "live" ] && { [ -n "$FIRST_PASS" ] || [ -n "$NEW_WATCH" ]; }; then
    echo "--first-pass and --new-watch are for the shadow deploy only; live needs BASE_URL in the secret" >&2
    exit 2
  fi
  if [ -n "$NEW_WATCH" ] && [ -z "$FIRST_PASS" ]; then
    echo "--new-watch goes with --first-pass (a new watch starts with a first-pass deploy)" >&2
    exit 2
  fi
  local url=""
  if [ "$EXPECT_MODE" = "live" ]; then
    # No preflight here: it must already have passed on this code, and the
    # stamp check is the only thing before the questions.
    python3 changesets/deploy/preflight_stamp.py check
    url="$(cat "$DEPLOY_DIR/web_url.txt" 2>/dev/null || true)"
    case "$url" in
      https://*) ;;
      *) echo "no https URL in $DEPLOY_DIR/web_url.txt: the shadow deploys write it. Not deployed." >&2; exit 1 ;;
    esac
  else
    preflight
  fi
  local count tiers
  count="$(python3 -c "import sys;sys.path.insert(0,'.');from services.reply_engine import modal_app;print(len(modal_app.SCHEDULED_FUNCTIONS))")"
  tiers="$(python3 -c "import sys;sys.path.insert(0,'.');from services.reply_engine import modal_app;print(','.join(modal_app.DEPLOY_TIERS))")"
  cat <<WARN

================================ READ THIS ================================
\`modal deploy\` registers all ${count} schedules at once (tiers: ${tiers}), plus
the web endpoint, and replaces whatever advero-reply-engine ran before.
They then run unattended, on Modal, in the mode the secret holds. This run
expects: ${EXPECT_MODE}. The list is in the summary printed above.

Laptop schedules are not deployed by this. The list factory, the only job
that spends through ALLOW_PAID_CALLS, runs on the laptop.

Rollback: \`python3 -m modal app stop advero-reply-engine\` stops every
schedule and the web endpoint at once (the fast kill switch). The Modal
Dicts survive a stop.

Live only: after DEPLOY this script creates the LIVE secret (modal_secret.py
asks for CREATE) and deploys right after it. From the moment the secret
exists, any NEW container of the running app reads it. If anything fails
after that, this script prints the abort sequence (runbooks/deployment.md
step 5, "If the live deploy fails"). Follow it at once.
===========================================================================
WARN
  if ! { : < /dev/tty; } 2>/dev/null; then
    echo "No terminal (/dev/tty) to read the DEPLOY answer from. Not deployed." >&2
    exit 1
  fi
  local answer=""
  read -r -p "Deploy advero-reply-engine with these ${count} schedules? [type DEPLOY] " answer < /dev/tty
  if [ "$answer" != "DEPLOY" ]; then
    echo "Not deployed."
    exit 1
  fi
  mkdir -p "$DEPLOY_DIR"
  if [ -n "$FIRST_PASS" ]; then
    # The hand-off start: before the first deploy, kept by a retried first
    # pass, fresh only with --new-watch. A refusal stops here, before deploying.
    python3 changesets/deploy/watch_clock.py begin ${NEW_WATCH}
  fi
  local log started
  log="$DEPLOY_DIR/deploy_$(date -u +%Y%m%dT%H%M%SZ).log"
  if [ "$EXPECT_MODE" = "live" ]; then
    # The live flip: the secret, then the deploy at once. Nothing between them.
    started="$(date -u +%Y-%m-%dT%H:%M:%S)"
    LIVE_SECRET_STATE="maybe"
    set +e
    python3 changesets/deploy/modal_secret.py --mode live --base-url "$url" --create
    local secret_code=$?
    set -e
    local outcome
    outcome="$(secret_outcome_since "$started" || echo none)"
    if [ "$outcome" = "none" ] && [ "$secret_code" -ne 0 ]; then
      # refused or not confirmed before `modal secret create` ran: nothing changed
      LIVE_SECRET_STATE="none"
    elif [ "$outcome" = "none" ]; then
      # exit 0 but no history record: it may exist, so the abort text still prints
      LIVE_SECRET_STATE="maybe"
    else
      LIVE_SECRET_STATE="$outcome"
    fi
    if [ "$LIVE_SECRET_STATE" != "created" ]; then
      echo "The live secret was not created (status: $LIVE_SECRET_STATE, exit $secret_code). Not deployed." >&2
      exit 1
    fi
  fi
  python3 -m modal deploy services/reply_engine/modal_app.py 2>&1 | tee "$log"
  # The web URL comes from THIS deploy's own output; the app listing prints no URLs.
  url="$(grep -Eo 'https://[A-Za-z0-9.-]*advero-reply-engine-web[A-Za-z0-9.-]*\.modal\.run' "$log" | head -1 || true)"
  if [ -z "$url" ] && [ "$EXPECT_MODE" = "live" ]; then
    # Live: the live secret is in place, so there is ONE next step, not a
    # manual one. The app's web URL does not change between deploys of the
    # same app, so /health is checked at the saved URL (the one the flip
    # started from). It passes: live is up. It fails: the exit trap prints
    # the abort sequence, and that is the only instruction.
    echo "Deployed, but the deploy output ($log) named no web URL. Checking /health at the saved URL instead:"
    echo "  $(cat "$DEPLOY_DIR/web_url.txt")"
  elif [ -z "$url" ]; then
    echo "Deployed, but no web URL was found in $log. Copy it from the deploy output into"
    echo "$DEPLOY_DIR/web_url.txt by hand, then run:"
    echo "  python3 changesets/deploy/verify_health.py --expect-mode $EXPECT_MODE ${FIRST_PASS}"
    return 1
  else
    echo "$url" > "$DEPLOY_DIR/web_url.txt"
    echo
    echo "web URL: $url   (saved to $DEPLOY_DIR/web_url.txt)"
  fi
  echo "== post-deploy: /health must report the expected mode =="
  python3 changesets/deploy/verify_health.py --expect-mode "$EXPECT_MODE" ${FIRST_PASS}
}

case "$MODE_ARG" in
  --preflight) preflight ;;
  --deploy)    deploy ;;
  *)
    echo "usage: $0 [--preflight | --deploy shadow|live [--first-pass] [--new-watch]]" >&2
    exit 2
    ;;
esac
