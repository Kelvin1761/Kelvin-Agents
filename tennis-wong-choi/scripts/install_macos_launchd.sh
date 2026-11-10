#!/bin/zsh
set -eu

# Installs the Tennis Wong Choi launchd jobs (Sydney time):
#
#   .night    21:00 精選 card for TOMORROW; 23:00 top-up (new picks only)
#   .card     09:00 backup: re-prices TODAY, 補充精選 only when new picks appear
#   .daily    18:00 settles yesterday, ROI board, archive, warms tomorrow
#   .recovery 10:30/12:30 reruns a failed 09:00 pass or a stale dashboard
#   .preclose every 30 min: near-start price of each 精選 match (closing price)
#   .settle   every hour at :35: settles finished 精選, redeploys if any settled
#
# Location-independent: WC_TENNIS_RUNTIME_ROOT points at the live data checkout
# (database, .venv, logs); the scripts run from this checkout.

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DEST_DIR="$HOME/Library/LaunchAgents"
DOMAIN="gui/$(id -u)"
TENNIS_RUNTIME_ROOT="${WC_TENNIS_RUNTIME_ROOT:-$PROJECT_DIR}"
DATABASE_PATH="$TENNIS_RUNTIME_ROOT/tennis_wc.db"
TENNIS_ENV_FILE="${TENNIS_ENV_FILE:-$TENNIS_RUNTIME_ROOT/.env}"
TENNIS_PYTHON_BIN="${TENNIS_PYTHON_BIN:-$TENNIS_RUNTIME_ROOT/.venv/bin/python}"
TENNIS_LOG_DIR="${TENNIS_LOG_DIR:-$TENNIS_RUNTIME_ROOT/data/logs}"
TENNIS_ANALYSIS_OUTPUT_ROOT="${TENNIS_ANALYSIS_OUTPUT_ROOT:-/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity}"
LABELS=(
  "com.antigravity.tennis-wong-choi.card"
  "com.antigravity.tennis-wong-choi.daily"
  "com.antigravity.tennis-wong-choi.recovery"
  "com.antigravity.tennis-wong-choi.preclose"
  "com.antigravity.tennis-wong-choi.night"
  "com.antigravity.tennis-wong-choi.settle"
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
elif [ "${1:-}" = "--preclose-only" ]; then
  # Same reasoning: adds the near-start capture without touching the others.
  LABELS=("com.antigravity.tennis-wong-choi.preclose")
elif [ "${1:-}" = "--night-only" ]; then
  # 21:00 精選 card + 23:00 top-up; safe to add without touching the others.
  LABELS=("com.antigravity.tennis-wong-choi.night")
elif [ "${1:-}" = "--settle-only" ]; then
  # Hourly 精選 settlement; safe to add without touching the others.
  LABELS=("com.antigravity.tennis-wong-choi.settle")
elif [ -n "${1:-}" ]; then
  echo "Usage: $0 [--recovery-only|--preclose-only|--night-only|--settle-only|--render-only DEST]" >&2
  exit 2
fi

if [ ! -f "$DATABASE_PATH" ]; then
  echo "ERROR: live Tennis database not found at $DATABASE_PATH" >&2
  echo "Set WC_TENNIS_RUNTIME_ROOT to the existing data checkout before cutover." >&2
  exit 1
fi
if [ ! -f "$TENNIS_ENV_FILE" ]; then
  echo "ERROR: live Tennis provider config not found at $TENNIS_ENV_FILE" >&2
  echo "Set TENNIS_ENV_FILE to the production .env before cutover." >&2
  exit 1
fi
if [ ! -x "$TENNIS_PYTHON_BIN" ]; then
  echo "ERROR: Tennis runtime interpreter not found at $TENNIS_PYTHON_BIN" >&2
  exit 1
fi

mkdir -p "$DEST_DIR" "$TENNIS_LOG_DIR"
chmod +x "$PROJECT_DIR/scripts/run_tennis_daily_schedule.sh" \
         "$PROJECT_DIR/scripts/tennis_daily_schedule.py" \
         "$PROJECT_DIR/scripts/tennis_card_recovery.py" \
         "$PROJECT_DIR/scripts/tennis_preclose_refresh.py" \
         "$PROJECT_DIR/scripts/tennis_settle_tick.py"

install_one() {
  local label="$1"
  local template="$PROJECT_DIR/launchd/$label.plist.template"
  local dest="$DEST_DIR/$label.plist"
  [ -f "$template" ] || { echo "ERROR: missing $template" >&2; exit 1; }
  local project_escaped database_escaped env_file_escaped python_escaped logs_escaped output_escaped
  project_escaped="$(printf '%s' "$PROJECT_DIR" | sed 's/[&#]/\\&/g')"
  database_escaped="$(printf '%s' "sqlite:///$DATABASE_PATH" | sed 's/[&#]/\\&/g')"
  env_file_escaped="$(printf '%s' "$TENNIS_ENV_FILE" | sed 's/[&#]/\\&/g')"
  python_escaped="$(printf '%s' "$TENNIS_PYTHON_BIN" | sed 's/[&#]/\\&/g')"
  logs_escaped="$(printf '%s' "$TENNIS_LOG_DIR" | sed 's/[&#]/\\&/g')"
  output_escaped="$(printf '%s' "$TENNIS_ANALYSIS_OUTPUT_ROOT" | sed 's/[&#]/\\&/g')"
  sed -e "s#__PROJECT_DIR__#$project_escaped#g" \
      -e "s#__DATABASE_URL__#$database_escaped#g" \
      -e "s#__TENNIS_ENV_FILE__#$env_file_escaped#g" \
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
echo "Provider config remains at $TENNIS_ENV_FILE"
echo "Runtime interpreter remains at $TENNIS_PYTHON_BIN"
echo "Analysis mirror remains at $TENNIS_ANALYSIS_OUTPUT_ROOT"
for label in "${LABELS[@]}"; do
  install_one "$label"
done

echo
echo "  21:00  night   — prices TOMORROW, sends 精選 (always); 23:00 top-up (new picks only)"
echo "  09:00  card    — backup: prices TODAY, sends 補充精選 only when new picks were added"
echo "  18:00  daily   — settles/reviews yesterday, archives, warms tomorrow"
echo "  10:30 + 12:30 recovery — missing card or dashboard-only retry, maximum twice each"
echo "  every 30 min  preclose — near-start odds capture for CLV (no card changes)"
echo "  hourly at :35 settle   — settles finished 精選, redeploys the dashboard if any settled"
echo "Logs: $TENNIS_LOG_DIR/"
echo
if [ "$RENDER_ONLY" -eq 1 ]; then
  echo "Rendered only; launchd was not changed."
else
  echo "Verify with:  launchctl list | grep tennis-wong-choi"
fi
