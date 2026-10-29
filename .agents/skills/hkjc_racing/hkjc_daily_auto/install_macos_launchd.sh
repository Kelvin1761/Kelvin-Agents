#!/bin/bash
set -eu

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RUNNER="$SCRIPT_DIR/run_hkjc_daily_schedule.sh"
LOG_DIR="$SCRIPT_DIR/logs"
AGENTS_DIR="$HOME/Library/LaunchAgents"

RENDER_ONLY=0
case "${1:-}" in
  --render-only)
    [ "$#" -eq 2 ] && [ -n "$2" ] || exit 2
    AGENTS_DIR="$2"
    RENDER_ONLY=1
    ;;
  "") ;;
  *) echo "Usage: $0 [--render-only DEST]" >&2; exit 2 ;;
esac
mkdir -p "$AGENTS_DIR"
if [ "$RENDER_ONLY" -eq 0 ]; then
  mkdir -p "$LOG_DIR"
  chmod +x "$RUNNER"
fi

for template in "$SCRIPT_DIR"/launchd/*.plist.template; do
  name="$(basename "$template" .template)"
  target="$AGENTS_DIR/$name"
  sed -e "s|__RUNNER__|$RUNNER|g" -e "s|__LOG_DIR__|$LOG_DIR|g" "$template" > "$target"
  chmod 644 "$target"
  [ "$RENDER_ONLY" -eq 0 ] || continue
  label="${name%.plist}"
  launchctl bootout "gui/$(id -u)/$label" >/dev/null 2>&1 || true
  launchctl bootstrap "gui/$(id -u)" "$target"
  echo "installed $label"
done
