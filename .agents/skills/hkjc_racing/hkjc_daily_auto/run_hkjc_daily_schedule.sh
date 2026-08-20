#!/bin/bash
set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
MODE="${1:-watch}"

cd "$REPO_ROOT" || exit 1

# Reuse AU Wong Choi's existing bot/chat without copying credentials into the repo.
NOTIFY_ENV="${WC_NOTIFY_ENV_FILE:-$HOME/.wongchoi_notify.env}"
[ -f "$NOTIFY_ENV" ] && source "$NOTIFY_ENV"

export PYTHONPATH="$REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}"
exec /usr/bin/python3 "$SCRIPT_DIR/hkjc_daily_schedule.py" --mode "$MODE"
