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
DEST_DIR="$HOME/Library/LaunchAgents"
DOMAIN="gui/$(id -u)"
TENNIS_RUNTIME_ROOT="${WC_TENNIS_RUNTIME_ROOT:-$PROJECT_DIR}"
DATABASE_PATH="$TENNIS_RUNTIME_ROOT/tennis_wc.db"
TENNIS_PYTHON_BIN="${TENNIS_PYTHON_BIN:-$TENNIS_RUNTIME_ROOT/.venv/bin/python}"
TENNIS_LOG_DIR="${TENNIS_LOG_DIR:-$TENNIS_RUNTIME_ROOT/data/logs}"
TENNIS_ANALYSIS_OUTPUT_ROOT="${TENNIS_ANALYSIS_OUTPUT_ROOT:-/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity}"
LABELS=(
  "com.antigravity.tennis-wong-choi.card"
  "com.antigravity.tennis-wong-choi.daily"
  "com.antigravity.tennis-wong-choi.recovery"
)

RENDER_ONLY=0
if [ "${1:-}" = "--render-only" ]; then
  [ -n "${2:-}" ] || { echo "--render-only requires a destination" >&2; exit 2; }
  DEST_DIR="$2"
  RENDER_ONLY=1
elif [ "${1:-}" = "--recovery-only" ]; then
  # Safe to use while the daily analysis is running: do not boot it out merely
  # to add the independent checker.
  LABELS=("com.antigravity.tennis-wong-choi.recovery")
elif [ -n "${1:-}" ]; then
  echo "Usage: $0 [--recovery-only|--render-only DEST]" >&2
  exit 2
fi

if [ ! -f "$DATABASE_PATH" ]; then
  echo "ERROR: live Tennis database not found at $DATABASE_PATH" >&2
  echo "Set WC_TENNIS_RUNTIME_ROOT to the existing data checkout before cutover." >&2
  exit 1
fi
if [ ! -x "$TENNIS_PYTHON_BIN" ]; then
  echo "ERROR: Tennis runtime interpreter not found at $TENNIS_PYTHON_BIN" >&2
  exit 1
fi

mkdir -p "$DEST_DIR" "$TENNIS_LOG_DIR"
chmod +x "$PROJECT_DIR/scripts/run_tennis_daily_schedule.sh" \
         "$PROJECT_DIR/scripts/tennis_daily_schedule.py" \
         "$PROJECT_DIR/scripts/tennis_card_recovery.py"

install_one() {
  local label="$1"
  local template="$PROJECT_DIR/launchd/$label.plist.template"
  local dest="$DEST_DIR/$label.plist"
  [ -f "$template" ] || { echo "ERROR: missing $template" >&2; exit 1; }
  local project_escaped database_escaped python_escaped logs_escaped output_escaped
  project_escaped="$(printf '%s' "$PROJECT_DIR" | sed 's/[&#]/\\&/g')"
  database_escaped="$(printf '%s' "sqlite:///$DATABASE_PATH" | sed 's/[&#]/\\&/g')"
  python_escaped="$(printf '%s' "$TENNIS_PYTHON_BIN" | sed 's/[&#]/\\&/g')"
  logs_escaped="$(printf '%s' "$TENNIS_LOG_DIR" | sed 's/[&#]/\\&/g')"
  output_escaped="$(printf '%s' "$TENNIS_ANALYSIS_OUTPUT_ROOT" | sed 's/[&#]/\\&/g')"
  sed -e "s#__PROJECT_DIR__#$project_escaped#g" \
      -e "s#__DATABASE_URL__#$database_escaped#g" \
      -e "s#__TENNIS_PYTHON_BIN__#$python_escaped#g" \
      -e "s#__TENNIS_LOG_DIR__#$logs_escaped#g" \
      -e "s#__TENNIS_ANALYSIS_OUTPUT_ROOT__#$output_escaped#g" "$template" > "$dest"
  chmod 644 "$dest"
  if [ "$RENDER_ONLY" -eq 1 ]; then
    echo "  rendered $label"
    return
  fi
  launchctl bootout "$DOMAIN" "$dest" 2>/dev/null || true
  launchctl bootstrap "$DOMAIN" "$dest"
  launchctl enable "$DOMAIN/$label"
  echo "  installed $label"
}

echo "Installing Tennis Wong Choi scheduled passes from $PROJECT_DIR"
echo "Live database/runtime remains at $TENNIS_RUNTIME_ROOT"
echo "Runtime interpreter remains at $TENNIS_PYTHON_BIN"
echo "Analysis mirror remains at $TENNIS_ANALYSIS_OUTPUT_ROOT"
for label in "${LABELS[@]}"; do
  install_one "$label"
done

echo
echo "  09:00  card    — prices TODAY, produces the betting card"
echo "  18:00  daily   — settles/reviews yesterday, archives, warms tomorrow"
echo "  10:30 + 12:30 recovery — missing card or dashboard-only retry, maximum twice each"
echo "Logs: $TENNIS_LOG_DIR/"
echo
if [ "$RENDER_ONLY" -eq 1 ]; then
  echo "Rendered only; launchd was not changed."
else
  echo "Verify with:  launchctl list | grep tennis-wong-choi"
fi
