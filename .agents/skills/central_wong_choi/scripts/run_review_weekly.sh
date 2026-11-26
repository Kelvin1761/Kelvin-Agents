#!/bin/zsh
# 每週 AI 覆盤總結（每星期一 09:30 悉尼，launchd）：Opus 讀過去 7 日四個 domain 嘅覆盤＋AI 解讀＋假設帳，Telegram primary。
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
print -r -- "== $(date '+%Y-%m-%d %H:%M:%S') review weekly"
exec /usr/bin/python3 "$PROJECT_ROOT/.agents/skills/shared_wong_choi/review_ai.py" weekly --telegram
