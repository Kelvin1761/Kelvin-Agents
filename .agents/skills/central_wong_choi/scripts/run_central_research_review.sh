#!/bin/zsh
# Stage 5 review only: explicit production locks, no credentials or self-update.
set -eu
SCRIPT_DIR="${0:A:h}"
PROJECT_ROOT="${WC_PRIMARY_REPO_ROOT:-${SCRIPT_DIR:h:h:h:h}}"
: "${WONGCHOI_CONTROL_STATE_ROOT:=$HOME/WongChoiData/WongChoiControl}"
: "${WC_WARM_ARCHIVE_ROOT:=/Volumes/Kelvin Hardisk 1/WongChoi-Archive}"
: "${WC_TENNIS_RUNTIME_ROOT:=$HOME/Antigravity-repo/tennis-wong-choi}"
: "${TENNIS_LOG_DIR:=$WC_TENNIS_RUNTIME_ROOT/data/logs}"
if [ -z "${WONGCHOI_AU_DATA_ROOT:-}" ] && [ -f "$HOME/.wongchoi_au_data_root" ]; then
  IFS= read -r WONGCHOI_AU_DATA_ROOT < "$HOME/.wongchoi_au_data_root"
fi
[ -n "${WONGCHOI_AU_DATA_ROOT:-}" ] || {
  print -u2 -- "AU production data root is required for research lock binding"
  exit 2
}
export WC_PRIMARY_REPO_ROOT WONGCHOI_CONTROL_STATE_ROOT WC_WARM_ARCHIVE_ROOT
cd "$PROJECT_ROOT"
exec "${WC_RESEARCH_PYTHON_BIN:-/usr/bin/python3}" \
  "$PROJECT_ROOT/.agents/skills/central_wong_choi/scripts/central_research_review.py" \
  --repo "$PROJECT_ROOT" --state-root "$WONGCHOI_CONTROL_STATE_ROOT" \
  --warm-root "$WC_WARM_ARCHIVE_ROOT" \
  --production-lock "$WONGCHOI_AU_DATA_ROOT/.au_daily_schedule.lock" \
  --production-lock "$PROJECT_ROOT/.agents/skills/hkjc_racing/hkjc_daily_auto/state/hkjc_daily_state.lock" \
  --production-lock "$PROJECT_ROOT/.agents/skills/nba/nba_daily_auto/state/nba_daily_schedule.lock" \
  --production-lock "$TENNIS_LOG_DIR/tennis_daily_schedule.lock" "$@"
