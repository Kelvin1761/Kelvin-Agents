#!/bin/zsh
# 安裝／重裝 AU Wong Choi 兩個每日 launchd job。
#
#   ./install_macos_launchd.sh            # 裝兩個
#   ./install_macos_launchd.sh --status   # 只睇狀態
#   ./install_macos_launchd.sh --uninstall
set -eu

SCRIPT_DIR="${0:A:h}"
PROJECT_ROOT="${SCRIPT_DIR:h:h:h:h}"
DEST_DIR="$HOME/Library/LaunchAgents"
UID_NUM="$(id -u)"
LABELS=(com.antigravity.au-wong-choi.evening com.antigravity.au-wong-choi.morning)

action="install"
[ "${1:-}" = "--status" ] && action="status"
[ "${1:-}" = "--uninstall" ] && action="uninstall"

if [ "$action" = "status" ]; then
  for label in $LABELS; do
    echo "── $label ──"
    launchctl print "gui/$UID_NUM/$label" 2>/dev/null \
      | grep -E "state =|last exit code|program =|runs =" || echo "  (未安裝)"
  done
  exit 0
fi

if [ "$action" = "uninstall" ]; then
  for label in $LABELS; do
    launchctl bootout "gui/$UID_NUM" "$DEST_DIR/$label.plist" 2>/dev/null || true
    rm -f "$DEST_DIR/$label.plist"
    echo "已移除 $label"
  done
  exit 0
fi

# 本機時區必須係 Australia/Sydney，否則 plist 嘅 22:00/10:00 唔係悉尼時間。
TZ_NAME="$(readlink /etc/localtime | sed 's#.*/zoneinfo/##')"
if [ "$TZ_NAME" != "Australia/Sydney" ]; then
  echo "⚠️  本機時區係 $TZ_NAME，唔係 Australia/Sydney。"
  echo "    launchd 用本機 wall clock，所以 22:00/10:00 唔會等於悉尼時間。"
  echo "    改機時區（系統設定 → 一般 → 日期與時間）之後再裝。"
  exit 1
fi

mkdir -p "$DEST_DIR" "$SCRIPT_DIR/logs"
chmod +x "$SCRIPT_DIR/run_au_daily_schedule.sh" "$SCRIPT_DIR/au_daily_schedule.py"

for label in $LABELS; do
  template="$SCRIPT_DIR/launchd/$label.plist.template"
  dest="$DEST_DIR/$label.plist"
  sed -e "s#__SCRIPT_DIR__#$SCRIPT_DIR#g" -e "s#__PROJECT_ROOT__#$PROJECT_ROOT#g" \
    "$template" > "$dest"
  chmod 644 "$dest"
  launchctl bootout "gui/$UID_NUM" "$dest" 2>/dev/null || true
  launchctl bootstrap "gui/$UID_NUM" "$dest"
  launchctl enable "gui/$UID_NUM/$label"
  echo "已安裝 $label"
done

echo
echo "排程（本機 = Australia/Sydney）："
echo "  com.antigravity.au-wong-choi.evening   每日 22:00  覆盤 → 歸檔 → 分析下一賽日 → 發佈"
echo "  com.antigravity.au-wong-choi.morning   每日 10:00  場地／退出馬覆核 → 需要時重評分 → 發佈"
echo
echo "Log：$SCRIPT_DIR/logs/"
