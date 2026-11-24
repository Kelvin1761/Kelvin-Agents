#!/bin/zsh
# 安裝每朝 04:00（悉尼）異地加密備份＋星期日還原演練。--status／--uninstall 同其他 central installer 一樣。
# 前提：已經跑過 `python3 .agents/scripts/offsite_backup.py init --backend r2:<bucket>`（或者 local:<第二隻碟>），
# 而且鑰匙已經抄落密碼管理器。未 init 就拒絕安裝 —— 冇設定嘅排程只會每晚失敗。
set -eu

SKILL_DIR="${0:A:h}"
SCRIPT_DIR="$SKILL_DIR/scripts"
PROJECT_ROOT="${SKILL_DIR:h:h:h}"
LABEL="com.antigravity.central-wong-choi.offsite-backup"
DEST="$HOME/Library/LaunchAgents/$LABEL.plist"
UID_NUM="$(id -u)"

case "${1:-}" in
  --status)
    launchctl print "gui/$UID_NUM/$LABEL" 2>/dev/null \
      | grep -E "state =|last exit code|program =|runs =" || print -r -- "(未安裝)"
    /usr/bin/python3 "$PROJECT_ROOT/.agents/scripts/offsite_backup.py" status
    exit 0
    ;;
  --uninstall)
    launchctl bootout "gui/$UID_NUM" "$DEST" 2>/dev/null || true
    rm -f "$DEST"
    print -r -- "已移除 $LABEL"
    exit 0
    ;;
esac

if [ ! -f "${WC_OFFSITE_CONFIG:-$HOME/.wongchoi_offsite.json}" ]; then
  print -r -- "未設定異地備份：先跑 offsite_backup.py init --backend r2:<bucket>；拒絕安裝。" >&2
  exit 1
fi
TZ_NAME="$(readlink /etc/localtime | sed 's#.*/zoneinfo/##')"
if [ "$TZ_NAME" != "Australia/Sydney" ]; then
  print -r -- "本機時區係 ${TZ_NAME}，唔係 Australia/Sydney；拒絕安裝。" >&2
  exit 1
fi

mkdir -p "$HOME/Library/LaunchAgents" "$SCRIPT_DIR/logs"
chmod +x "$SCRIPT_DIR/run_offsite_backup.sh"
sed -e "s#__SCRIPT_DIR__#$SCRIPT_DIR#g" -e "s#__PROJECT_ROOT__#$PROJECT_ROOT#g" \
  "$SKILL_DIR/launchd/$LABEL.plist.template" > "$DEST"
chmod 644 "$DEST"
launchctl bootout "gui/$UID_NUM" "$DEST" 2>/dev/null || true
launchctl bootstrap "gui/$UID_NUM" "$DEST"
launchctl enable "gui/$UID_NUM/$LABEL"
print -r -- "已安裝 ${LABEL}：每朝悉尼 04:00 異地加密備份，星期日還原演練"
