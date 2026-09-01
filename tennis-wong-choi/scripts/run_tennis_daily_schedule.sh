#!/bin/zsh
set -eu

# Location-independent: works from the local repo (post 2026-07-14 migration)
# and from any other checkout — the project dir is wherever this script lives.
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
REPO_ROOT="$(cd "$PROJECT_DIR/.." && pwd)"
CONTROL_PLANE="$REPO_ROOT/.agents/skills/shared_wong_choi/control_plane.py"
cd "$PROJECT_DIR"

# Backward compatible with the external launcher: historically it passed only
# --refresh-today for the 09:00 card and no positional mode for the 18:00 run.
MODE="daily"
if [ "${1:-}" = "card" ] || [ "${1:-}" = "daily" ]; then
  MODE="$1"
  shift
elif [[ " $* " = *" --refresh-today "* ]]; then
  MODE="card"
fi

if [ -n "${TENNIS_PYTHON_BIN:-}" ] && [ -x "$TENNIS_PYTHON_BIN" ]; then
  PYTHON_BIN="$TENNIS_PYTHON_BIN"
elif [ -x ".venv/bin/python" ]; then
  PYTHON_BIN=".venv/bin/python"
else
  PYTHON_BIN="python3"
fi

# launchd cannot enumerate the HKJC Google Drive folder.  Start from the live
# race snapshot and let generate_static rebuild only the local multi-sport feed;
# otherwise a valid Tennis card can be followed by a guaranteed TCC failure.
SNAPSHOT_DIR="$PROJECT_DIR/data/runtime"
SNAPSHOT_PATH="$SNAPSHOT_DIR/live-dashboard-data.json"
SNAPSHOT_TMP="$SNAPSHOT_PATH.tmp.$$"
SNAPSHOT_URL="https://wongchoi-dashboard.pages.dev/dashboard-data.json?cb=$(date +%s)"
mkdir -p "$SNAPSHOT_DIR"
if /usr/bin/curl --fail --silent --show-error --location \
    --connect-timeout 15 --max-time 60 \
    -H "Cache-Control: no-cache, max-age=0" \
    -o "$SNAPSHOT_TMP" "$SNAPSHOT_URL" \
    && "$PYTHON_BIN" -c 'import json,sys; json.load(open(sys.argv[1], encoding="utf-8"))' "$SNAPSHOT_TMP"; then
  mv "$SNAPSHOT_TMP" "$SNAPSHOT_PATH"
  export WC_DASHBOARD_BASE_SNAPSHOT="$SNAPSHOT_PATH"
else
  rm -f "$SNAPSHOT_TMP"
  print -u2 -- "WARNING: live dashboard snapshot unavailable; analysis will continue and deploy may be retried later."
fi

exec "$PYTHON_BIN" "$CONTROL_PLANE" --domain tennis --mode "$MODE" "$@"
