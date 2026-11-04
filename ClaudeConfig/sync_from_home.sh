#!/bin/sh
# Repository instructions are maintained here. Audit first; never rsync --delete.
# --import-new copies additions; --replace PATH backs up an explicit conflict.
set -eu
cd "$(dirname "$0")/.."
exec /usr/bin/python3 ClaudeConfig/tools/sync_config.py "$@"
