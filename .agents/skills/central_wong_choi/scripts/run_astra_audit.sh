#!/bin/zsh
# Astra 每週深度審計（每星期一 08:00 悉尼，launchd）。只做診斷，結果 Telegram primary。
set -eu

SCRIPT_DIR="${0:A:h}"
PROJECT_ROOT="${SCRIPT_DIR:h:h:h:h}"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8

: "${WONGCHOI_CONTROL_STATE_ROOT:=$HOME/WongChoiData/WongChoiControl}"
export WONGCHOI_CONTROL_STATE_ROOT

[ -f "$HOME/.wongchoi_notify.env" ] && source "$HOME/.wongchoi_notify.env"

cd "$PROJECT_ROOT"
print -r -- "== $(date '+%Y-%m-%d %H:%M:%S') Astra weekly audit"
exec /usr/bin/python3 "$SCRIPT_DIR/astra_weekly_audit.py"
