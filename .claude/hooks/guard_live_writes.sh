#!/bin/sh
# Compatibility for sessions that cached the removed live-write hook registration.
# Lorenzo retired this hook on 2026-10-10. New sessions use .codex/hooks.json.
# Live-write enforcement remains in the engine's shared.settings.guard_write.
exit 0
