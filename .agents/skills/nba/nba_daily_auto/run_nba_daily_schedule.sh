#!/bin/bash
set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"

  LEASE_HELPER="$REPO_ROOT/.agents/skills/shared_wong_choi/runtime_cutover_lease.py"
  if [ -z "${WC_RUNTIME_CUTOVER_FD:-}" ]; then
    exec /usr/bin/python3 "$LEASE_HELPER" --mode shared -- /bin/bash "$0" "$@"
  fi
  /usr/bin/python3 "$LEASE_HELPER" --mode shared --verify || exit $?

CONTROL_PLANE="$REPO_ROOT/.agents/skills/shared_wong_choi/control_plane.py"
MODE="${1:-health}"
[ "$#" -gt 0 ] && shift

cd "$REPO_ROOT" || exit 1

# 追上 origin/main。⚠️ 五個排程共用同一個 worktree，而 2026-09-09 之前**只有 AU
# 個 wrapper 會 ff** —— 其餘四個更新 code 全靠 AU 啱啱好有開工帶挈。AU 一停，
# 佢哋就無限期跑舊 code 而冇任何嘢會投訴。失敗唔會阻開工（見個 script 頭）。
if [[ "$MODE" != "postgame" ]]; then
  /usr/bin/python3 "$REPO_ROOT/.agents/scripts/wongchoi_self_update.py" "$REPO_ROOT" || true
fi
NOTIFY_ENV="${WC_NOTIFY_ENV_FILE:-$HOME/.wongchoi_notify.env}"
[ -f "$NOTIFY_ENV" ] && source "$NOTIFY_ENV"

# Keep launchd away from Google Drive File Provider. The analysis card remains
# in the repo root while live; completed days move to this local archive.
export WONGCHOI_NBA_DATA_ROOT="${WONGCHOI_NBA_DATA_ROOT:-$HOME/WongChoiData/Wong Choi NBA Analysis}"
# Prefer a hydrated local copy of the existing model for unattended runs.
# An explicit model directory remains authoritative; missing cache preserves
# the configured dataset path and the engine's existing fallback behaviour.
NBA_LOCAL_MODEL_DIR="$HOME/WongChoiData/NBA_ML_Dataset/models/v3"
if [[ -z "${NBA_WC_MODEL_DIR:-}" && -s "$NBA_LOCAL_MODEL_DIR/model.pkl" && -s "$NBA_LOCAL_MODEL_DIR/feature_names.json" ]]; then
  export NBA_WC_MODEL_DIR="$NBA_LOCAL_MODEL_DIR"
fi
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}"
mkdir -p "$WONGCHOI_NBA_DATA_ROOT"

# Each results poll needs its own idempotent slot; retries retain that request.
if [[ "$MODE" == "postgame" ]]; then
  RESULTS_MINUTE="$(TZ=Australia/Sydney date +%M)"
  RESULTS_QUARTER=$((10#$RESULTS_MINUTE / 15 * 15))
  set -- --scheduled-slot "postgame-$(TZ=Australia/Sydney date +%Y%m%d-%H)-${RESULTS_QUARTER}" "$@"
fi
exec /usr/bin/python3 "$CONTROL_PLANE" --domain nba --mode "$MODE" "$@"
