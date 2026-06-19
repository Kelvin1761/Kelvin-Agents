#!/bin/zsh
set -eu

PROJECT_DIR="/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity/tennis-wong-choi"
cd "$PROJECT_DIR"

if [ -x ".venv/bin/python" ]; then
  exec ".venv/bin/python" "scripts/tennis_daily_schedule.py" "$@"
fi

exec "python3" "scripts/tennis_daily_schedule.py" "$@"
