#!/usr/bin/env bash
# Local shadow server for the reply engine on http://127.0.0.1:8787
#
# Controlled environment: MODE is forced to shadow and ALLOW_LIVE_WRITES is
# removed from the environment, so nothing this process does can reach live
# Instantly or GHL. shared.settings.load_env() loads "Agentic Worklfows/.env"
# (then AdveroSolutions/.env) at import, so API keys come from there without
# sourcing the file into the shell.
#
# A push is a guarded write too, so in shadow notify() records the intent and
# delivers nothing. This laptop instance does not need pushes (its evidence is
# .tmp/shadow_log.jsonl and .tmp/job_log.csv on disk), so NOTIFY_SHADOW_SEND is
# left alone here; on Modal it is set in the secret, because there the phone is
# the only place the shadow watch is visible (runbooks/deployment.md step 2a).
#
# Usage:  bash services/reply_engine/run_local.sh            (from Agentic Worklfows/)
#         PORT=8788 bash services/reply_engine/run_local.sh
#         NOTIFY_SHADOW_SEND=1 bash services/reply_engine/run_local.sh   (also push to the phone)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE="$(cd "$HERE/../.." && pwd)"
cd "$BASE"

export MODE=shadow
unset ALLOW_LIVE_WRITES || true
export RUNTIME=local
export PORT="${PORT:-8787}"
export PYTHONPATH="$BASE${PYTHONPATH:+:$PYTHONPATH}"

if [ ! -f "$BASE/.env" ]; then
  echo "warning: $BASE/.env not found; INSTANTLY_API_KEY must be in the environment" >&2
fi

if ! python3 -c "import uvicorn" 2>/dev/null; then
  echo "uvicorn is not installed for python3. Install the pinned runtime in a venv first:" >&2
  echo "  python3 -m venv .venv && . .venv/bin/activate && pip install -r services/reply_engine/requirements.txt" >&2
  exit 1
fi

if ! python3 -c "import services.reply_engine.app" 2>/dev/null; then
  echo "services/reply_engine/app.py is not importable yet (owned by the A1 brief); nothing to serve." >&2
  exit 1
fi

echo "reply engine: MODE=$MODE RUNTIME=$RUNTIME on http://127.0.0.1:$PORT (shadow: no live writes)"
exec python3 -m uvicorn services.reply_engine.app:app --host 127.0.0.1 --port "$PORT" --reload
