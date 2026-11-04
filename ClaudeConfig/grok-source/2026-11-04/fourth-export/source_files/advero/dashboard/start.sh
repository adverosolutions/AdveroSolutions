#!/bin/bash
# Idempotent: start tailscaled (no systemd on this box) and the dashboard supervisor if not running.
cd "$(dirname "$0")"
[ -e /var/run ] || sudo ln -s /run /var/run
pgrep -x tailscaled >/dev/null || sudo sh -c 'nohup tailscaled --state=/var/lib/tailscale/tailscaled.state --socket=/run/tailscale/tailscaled.sock >/var/log/tailscaled.log 2>&1 &'
if [ -f logs/supervisor.pid ] && kill -0 "$(cat logs/supervisor.pid)" 2>/dev/null; then echo "dashboard supervisor already running"; exit 0; fi
mkdir -p logs; setsid nohup ./run_dashboard.sh >/dev/null 2>&1 < /dev/null &
echo "started"
