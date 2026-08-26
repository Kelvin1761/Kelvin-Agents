#!/bin/bash
set -eu

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RUNNER="$SCRIPT_DIR/run_nba_daily_schedule.sh"
LOG_DIR="$SCRIPT_DIR/logs"
DEST_DIR="$HOME/Library/LaunchAgents"
DOMAIN="gui/$(id -u)"
LEGACY_PREGAME_LABEL="com.antigravity.nba-wong-choi.pregame"

status() {
  for template in "$SCRIPT_DIR"/launchd/*.plist.template; do
    label="$(basename "$template" .plist.template)"
    if launchctl print "$DOMAIN/$label" >/dev/null 2>&1; then
      detail="$(launchctl print "$DOMAIN/$label" 2>/dev/null || true)"
      exit_code="$(printf '%s\n' "$detail" | sed -n 's/^[[:space:]]*last exit code = //p' | head -1)"
      echo "loaded  $label  last_exit=${exit_code:-never}"
    else
      echo "missing $label"
    fi
  done
}

uninstall() {
  for template in "$SCRIPT_DIR"/launchd/*.plist.template; do
    label="$(basename "$template" .plist.template)"
    target="$DEST_DIR/$label.plist"
    launchctl bootout "$DOMAIN/$label" >/dev/null 2>&1 || true
    [ ! -e "$target" ] || mv "$target" "$target.disabled"
    echo "uninstalled $label"
  done
  legacy_target="$DEST_DIR/$LEGACY_PREGAME_LABEL.plist"
  launchctl bootout "$DOMAIN/$LEGACY_PREGAME_LABEL" >/dev/null 2>&1 || true
  [ ! -e "$legacy_target" ] || mv "$legacy_target" "$legacy_target.disabled"
}

case "${1:-}" in
  --status) status; exit 0 ;;
  --uninstall) uninstall; exit 0 ;;
  "") ;;
  *) echo "Usage: $0 [--status|--uninstall]" >&2; exit 2 ;;
esac

mkdir -p "$LOG_DIR" "$DEST_DIR" "$HOME/WongChoiData/Wong Choi NBA Analysis"
chmod +x "$RUNNER" "$SCRIPT_DIR/nba_daily_schedule.py"

# Before 2026-08-26 all three pregame times shared one label.  Remove it first
# so upgrading cannot leave the legacy job firing beside the role-specific jobs.
legacy_target="$DEST_DIR/$LEGACY_PREGAME_LABEL.plist"
launchctl bootout "$DOMAIN/$LEGACY_PREGAME_LABEL" >/dev/null 2>&1 || true
[ ! -e "$legacy_target" ] || mv "$legacy_target" "$legacy_target.disabled"

for template in "$SCRIPT_DIR"/launchd/*.plist.template; do
  name="$(basename "$template" .template)"
  target="$DEST_DIR/$name"
  sed -e "s|__RUNNER__|$RUNNER|g" -e "s|__LOG_DIR__|$LOG_DIR|g" "$template" > "$target"
  chmod 644 "$target"
  label="${name%.plist}"
  launchctl bootout "$DOMAIN/$label" >/dev/null 2>&1 || true
  launchctl bootstrap "$DOMAIN" "$target"
  launchctl enable "$DOMAIN/$label"
  echo "installed $label"
done

echo
echo "NBA Wong Choi automation installed:"
echo "  warmup   21:00 (tomorrow; no publish/content card)"
echo "  pregame  00:30 production + 06:30 unstarted-only final refresh"
echo "  postgame 18:30 + 21:30"
echo "  health   10:30"
echo "  startup  login catch-up"
echo "Logs: $LOG_DIR"
status
