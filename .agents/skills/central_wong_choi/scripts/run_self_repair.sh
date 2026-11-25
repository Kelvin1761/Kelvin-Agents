#!/bin/zsh
# 排程自動維修（launchd 每 30 分鐘）。參數照傳：預設 dry-run；--live 先真係修。
set -eu

SCRIPT_DIR="${0:A:h}"
PROJECT_ROOT="${SCRIPT_DIR:h:h:h:h}"

: "${WONGCHOI_CONTROL_STATE_ROOT:=$HOME/WongChoiData/WongChoiControl}"
export WONGCHOI_CONTROL_STATE_ROOT
# --allow-llm-diagnosis 要搵到 claude CLI
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

[ -f "$HOME/.wongchoi_notify.env" ] && source "$HOME/.wongchoi_notify.env"

cd "$PROJECT_ROOT"
print -r -- "== $(date '+%Y-%m-%d %H:%M:%S') self-repair ${*:-(dry-run)}"
exec /usr/bin/python3 "$PROJECT_ROOT/.agents/scripts/self_repair.py" "$@"
