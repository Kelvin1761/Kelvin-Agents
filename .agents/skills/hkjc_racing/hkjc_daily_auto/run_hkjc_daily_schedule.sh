#!/bin/bash
set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
CONTROL_PLANE="$REPO_ROOT/.agents/skills/shared_wong_choi/control_plane.py"
MODE="${1:-watch}"
[ "$#" -gt 0 ] && shift

cd "$REPO_ROOT" || exit 1

# Pull the shared scheduler worktree forward before starting.  Failure is
# deliberately non-fatal: the run can continue on the currently checked-out
# version and the helper emits the operational warning.
/usr/bin/python3 "$REPO_ROOT/.agents/scripts/wongchoi_self_update.py" "$REPO_ROOT" || true

# Reuse AU Wong Choi's existing bot/chat without copying credentials into the repo.
NOTIFY_ENV="${WC_NOTIFY_ENV_FILE:-$HOME/.wongchoi_notify.env}"
[ -f "$NOTIFY_ENV" ] && source "$NOTIFY_ENV"

export PYTHONPATH="$REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}"

# Weekly is a model-promotion review gate, not a normal event lifecycle run.
# Keep it outside the prediction control contract.
# Weekly is a release review and intraday is a read-only prospective evidence
# collector; neither is a new event prediction lifecycle run.
if [ "$MODE" = "weekly" ] || [ "$MODE" = "intraday" ]; then
  exec /usr/bin/python3 "$SCRIPT_DIR/hkjc_daily_schedule.py" --mode "$MODE" "$@"
fi
exec /usr/bin/python3 "$CONTROL_PLANE" --domain hkjc --mode "$MODE" "$@"
