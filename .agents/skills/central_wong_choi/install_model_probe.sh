#!/bin/zsh
# 安裝每朝 07:30（悉尼）委派模型探測。--status／--uninstall 同 durability 一樣。
set -eu

SKILL_DIR="${0:A:h}"
SCRIPT_DIR="$SKILL_DIR/scripts"
PROJECT_ROOT="${SKILL_DIR:h:h:h}"
LABEL="com.antigravity.central-wong-choi.model-probe"
DEST="$HOME/Library/LaunchAgents/$LABEL.plist"
UID_NUM="$(id -u)"

case "${1:-}" in
  --status)
    launchctl print "gui/$UID_NUM/$LABEL" 2>/dev/null \
      | grep -E "state =|last exit code|program =|runs =" || print -r -- "(未安裝)"
    exit 0
    ;;
  --uninstall)
    launchctl bootout "gui/$UID_NUM" "$DEST" 2>/dev/null || true
    rm -f "$DEST"
    print -r -- "已移除 $LABEL"
    exit 0
    ;;
esac

TZ_NAME="$(readlink /etc/localtime | sed 's#.*/zoneinfo/##')"
if [ "$TZ_NAME" != "Australia/Sydney" ]; then
  print -r -- "本機時區係 ${TZ_NAME}，唔係 Australia/Sydney；拒絕安裝。" >&2
  exit 1
fi

mkdir -p "$HOME/Library/LaunchAgents" "$SCRIPT_DIR/logs"
chmod +x "$SCRIPT_DIR/run_model_probe.sh"
sed -e "s#__SCRIPT_DIR__#$SCRIPT_DIR#g" -e "s#__PROJECT_ROOT__#$PROJECT_ROOT#g" \
  "$SKILL_DIR/launchd/$LABEL.plist.template" > "$DEST"
chmod 644 "$DEST"
launchctl bootout "gui/$UID_NUM" "$DEST" 2>/dev/null || true
launchctl bootstrap "gui/$UID_NUM" "$DEST"
launchctl enable "gui/$UID_NUM/$LABEL"
print -r -- "已安裝 ${LABEL}：每朝悉尼時間 07:30 探測委派模型（唔正常先通知 Kelvin）"
