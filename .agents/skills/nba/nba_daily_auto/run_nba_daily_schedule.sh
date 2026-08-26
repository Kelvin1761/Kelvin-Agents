#!/bin/bash
set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
CONTROL_PLANE="$REPO_ROOT/.agents/skills/shared_wong_choi/control_plane.py"
MODE="${1:-health}"
[ "$#" -gt 0 ] && shift

cd "$REPO_ROOT" || exit 1
NOTIFY_ENV="${WC_NOTIFY_ENV_FILE:-$HOME/.wongchoi_notify.env}"
[ -f "$NOTIFY_ENV" ] && source "$NOTIFY_ENV"

# Keep launchd away from Google Drive File Provider. The analysis card remains
# in the repo root while live; completed days move to this local archive.
export WONGCHOI_NBA_DATA_ROOT="${WONGCHOI_NBA_DATA_ROOT:-$HOME/WongChoiData/Wong Choi NBA Analysis}"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}"
mkdir -p "$WONGCHOI_NBA_DATA_ROOT"

exec /usr/bin/python3 "$CONTROL_PLANE" --domain nba --mode "$MODE" "$@"
