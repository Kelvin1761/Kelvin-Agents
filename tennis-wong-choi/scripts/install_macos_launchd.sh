#!/bin/zsh
set -eu

# Installs the two scheduled passes plus guarded card recovery.
#
#   .card   09:00 — produces the betting card for TODAY (--refresh-today)
#   .daily  18:00 — settles and reviews yesterday, archives, warms tomorrow
#   .recovery 10:30/12:30 — restores a missing card OR a stale dashboard
#
# The split exists because Sportsbet does not open tomorrow's book in the
# evening. Its own listing returns HTTP 200 and two bytes at 18:07 and 55
# events for the same date at 09:08, so the evening job structurally cannot
# price the card. Before 2026-08-11 it was the only scheduled job; the morning
# pass was run by hand, and when that stopped the pipeline ran three days dark
# while every evening's log looked normal.
#
# 09:00 is also the price the backtest measured: `earliest_odds=True` takes
# each selection's first snapshot, which for almost every date is this run.
#
# Location-independent, unlike the version this replaces, which still pointed
# at the Google Drive path the repo left in the 2026-07-14 migration.

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LAUNCHER="$HOME/Library/Application Support/TennisWongChoi/run_launcher.sh"
DEST_DIR="$HOME/Library/LaunchAgents"
DOMAIN="gui/$(id -u)"
LABELS=(
  "com.antigravity.tennis-wong-choi.card"
  "com.antigravity.tennis-wong-choi.daily"
  "com.antigravity.tennis-wong-choi.recovery"
)

if [ "${1:-}" = "--recovery-only" ]; then
  # Safe to use while the daily analysis is running: do not boot it out merely
  # to add the independent checker.
  LABELS=("com.antigravity.tennis-wong-choi.recovery")
elif [ -n "${1:-}" ]; then
  echo "Usage: $0 [--recovery-only]" >&2
  exit 2
fi

if [ ! -f "$LAUNCHER" ]; then
  echo "ERROR: launcher not found at $LAUNCHER" >&2
  echo "It sets TENNIS_ANALYSIS_OUTPUT_ROOT and lives outside the repo on purpose." >&2
  exit 1
fi

mkdir -p "$DEST_DIR" "$PROJECT_DIR/data/logs"
chmod +x "$PROJECT_DIR/scripts/run_tennis_daily_schedule.sh" \
         "$PROJECT_DIR/scripts/tennis_daily_schedule.py" \
         "$PROJECT_DIR/scripts/tennis_card_recovery.py"

install_one() {
  local label="$1"
  local template="$PROJECT_DIR/launchd/$label.plist.template"
  local dest="$DEST_DIR/$label.plist"
  [ -f "$template" ] || { echo "ERROR: missing $template" >&2; exit 1; }
  sed -e "s#__PROJECT_DIR__#$PROJECT_DIR#g" \
      -e "s#__LAUNCHER__#$LAUNCHER#g" "$template" > "$dest"
  chmod 644 "$dest"
  launchctl bootout "$DOMAIN" "$dest" 2>/dev/null || true
  launchctl bootstrap "$DOMAIN" "$dest"
  launchctl enable "$DOMAIN/$label"
  echo "  installed $label"
}

echo "Installing Tennis Wong Choi scheduled passes from $PROJECT_DIR"
for label in "${LABELS[@]}"; do
  install_one "$label"
done

echo
echo "  09:00  card    — prices TODAY, produces the betting card"
echo "  18:00  daily   — settles/reviews yesterday, archives, warms tomorrow"
echo "  10:30 + 12:30 recovery — missing card or dashboard-only retry, maximum twice each"
echo "Logs: $PROJECT_DIR/data/logs/"
echo
echo "Verify with:  launchctl list | grep tennis-wong-choi"
