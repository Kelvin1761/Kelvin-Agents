#!/bin/zsh
# 旺財每日 ROI 總結（每朝 09:00 悉尼，launchd）。
# 讀 AU／NBA／網球結算時寫入嘅統一 ROI ledger，發一條總結俾 Kelvin + Heison。
# 唔重新計數 —— 數字由各旺財自己結算嗰陣寫入（wongchoi_roi.py）。
set -eu

SCRIPT_DIR="${0:A:h}"
PROJECT_ROOT="${SCRIPT_DIR:h:h:h:h}"

: "${WONGCHOI_CONTROL_STATE_ROOT:=$HOME/WongChoiData/WongChoiControl}"
export WONGCHOI_CONTROL_STATE_ROOT

[ -f "$HOME/.wongchoi_notify.env" ] && source "$HOME/.wongchoi_notify.env"

cd "$PROJECT_ROOT"
print -r -- "== $(date '+%Y-%m-%d %H:%M:%S') ROI summary"
exec /usr/bin/python3 "$PROJECT_ROOT/.agents/skills/shared_racing/scripts/wongchoi_roi.py" --summary
