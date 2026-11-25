#!/bin/zsh
# 委派模型每日探測（每朝 07:30 悉尼，launchd）：Luna／Terra／Sol／Astra／Hydrogen 各試一句，唔正常先 Telegram primary。
set -eu

SCRIPT_DIR="${0:A:h}"
PROJECT_ROOT="${SCRIPT_DIR:h:h:h:h}"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8

: "${WONGCHOI_CONTROL_STATE_ROOT:=$HOME/WongChoiData/WongChoiControl}"
export WONGCHOI_CONTROL_STATE_ROOT

[ -f "$HOME/.wongchoi_notify.env" ] && source "$HOME/.wongchoi_notify.env"

cd "$PROJECT_ROOT"
# 開工前追上 origin/main（每個排程 wrapper 都要；失敗唔阻開工）
/usr/bin/python3 "$PROJECT_ROOT/.agents/scripts/wongchoi_self_update.py" "$PROJECT_ROOT" || true
print -r -- "== $(date '+%Y-%m-%d %H:%M:%S') model probe"
exec /usr/bin/python3 "$PROJECT_ROOT/.agents/scripts/codex_delegate.py" health --probe
