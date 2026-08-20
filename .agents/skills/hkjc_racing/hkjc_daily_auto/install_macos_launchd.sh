#!/bin/bash
set -eu

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RUNNER="$SCRIPT_DIR/run_hkjc_daily_schedule.sh"
LOG_DIR="$SCRIPT_DIR/logs"
AGENTS_DIR="$HOME/Library/LaunchAgents"

mkdir -p "$LOG_DIR" "$AGENTS_DIR"
chmod +x "$RUNNER"

for template in "$SCRIPT_DIR"/launchd/*.plist.template; do
  name="$(basename "$template" .template)"
  target="$AGENTS_DIR/$name"
  sed -e "s|__RUNNER__|$RUNNER|g" -e "s|__LOG_DIR__|$LOG_DIR|g" "$template" > "$target"
  label="${name%.plist}"
  launchctl bootout "gui/$(id -u)/$label" >/dev/null 2>&1 || true
  launchctl bootstrap "gui/$(id -u)" "$target"
  echo "installed $label"
done
