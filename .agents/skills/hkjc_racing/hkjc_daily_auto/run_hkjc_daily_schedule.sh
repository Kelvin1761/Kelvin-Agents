#!/bin/bash
set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
MODE="${1:-watch}"

cd "$REPO_ROOT" || exit 1
export PYTHONPATH="$REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}"
exec /usr/bin/python3 "$SCRIPT_DIR/hkjc_daily_schedule.py" --mode "$MODE"
