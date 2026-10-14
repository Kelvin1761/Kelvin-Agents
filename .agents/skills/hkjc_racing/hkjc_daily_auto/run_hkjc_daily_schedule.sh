#!/bin/bash
set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
CONTROL_PLANE="$REPO_ROOT/.agents/skills/shared_wong_choi/control_plane.py"
MODE="${1:-watch}"
[ "$#" -gt 0 ] && shift

cd "$REPO_ROOT" || exit 1
if [ "$MODE" = "deferred" ] || PYTHONPATH="$REPO_ROOT/.agents/skills" /usr/bin/python3 -c 'from datetime import datetime; from shared_wong_choi.scheduler_window import SYDNEY, quiet_until; import sys; sys.exit(0 if quiet_until(datetime.now(SYDNEY)) else 1)'; then
  exec /usr/bin/python3 "$CONTROL_PLANE" --domain hkjc --mode "$MODE" "$@"
fi


# Pull the shared scheduler worktree forward before starting.  Failure is
# deliberately non-fatal: the run can continue on the currently checked-out
# version and the helper emits the operational warning.
/usr/bin/python3 "$REPO_ROOT/.agents/scripts/wongchoi_self_update.py" "$REPO_ROOT" || true

# Reuse AU Wong Choi's existing bot/chat without copying credentials into the repo.
NOTIFY_ENV="${WC_NOTIFY_ENV_FILE:-$HOME/.wongchoi_notify.env}"
[ -f "$NOTIFY_ENV" ] && source "$NOTIFY_ENV"

export PYTHONPATH="$REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}"

exec /usr/bin/python3 "$CONTROL_PLANE" --domain hkjc --mode "$MODE" "$@"
