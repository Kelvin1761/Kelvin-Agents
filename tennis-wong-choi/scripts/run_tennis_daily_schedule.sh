#!/bin/zsh
set -eu

PROJECT_DIR="/Users/imac/dev/Antigravity/tennis-wong-choi"
cd "$PROJECT_DIR"

if [ -x ".venv/bin/python" ]; then
  exec ".venv/bin/python" "scripts/tennis_daily_schedule.py" "$@"
fi

exec "python3" "scripts/tennis_daily_schedule.py" "$@"
