#!/bin/zsh
# 每週健康巡查（每星期一 07:30 悉尼，launchd）：Hydrogen 抽查原文對入分欄位＋讀欄位趨勢，Python 核實，Telegram primary。
set -eu

SCRIPT_DIR="${0:A:h}"
PROJECT_ROOT="${SCRIPT_DIR:h:h:h:h}"
export PATH="/opt/homebrew/bin:$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8

: "${WONGCHOI_CONTROL_STATE_ROOT:=$HOME/WongChoiData/WongChoiControl}"
export WONGCHOI_CONTROL_STATE_ROOT

[ -f "$HOME/.wongchoi_notify.env" ] && source "$HOME/.wongchoi_notify.env"

cd "$PROJECT_ROOT"
# 開工前追上 origin/main（每個排程 wrapper 都要；失敗唔阻開工）
/usr/bin/python3 "$PROJECT_ROOT/.agents/scripts/wongchoi_self_update.py" "$PROJECT_ROOT" || true
print -r -- "== $(date '+%Y-%m-%d %H:%M:%S') health sweep"
exec /usr/bin/python3 "$PROJECT_ROOT/.agents/skills/shared_wong_choi/health_sweep.py" --telegram
