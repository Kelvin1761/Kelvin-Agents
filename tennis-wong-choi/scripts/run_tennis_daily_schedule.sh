#!/bin/zsh
set -eu

# Location-independent: works from the local repo (post 2026-07-14 migration)
# and from any other checkout — the project dir is wherever this script lives.
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

if [ -x ".venv/bin/python" ]; then
  exec ".venv/bin/python" "scripts/tennis_daily_schedule.py" "$@"
fi

exec "python3" "scripts/tennis_daily_schedule.py" "$@"
