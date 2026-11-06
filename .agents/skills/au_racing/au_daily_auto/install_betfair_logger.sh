#!/bin/zsh
# EXP-20261106-02：安裝／移除 Betfair 市場走勢記錄器嘅兩個 launchd job（唔郁其他 AU job）。只讀市場，唔落注。
#
#   ./install_betfair_logger.sh --check       # 用 ~/.wongchoi_betfair.env 試一次登入＋快照（唔裝）
#   ./install_betfair_logger.sh               # 裝（每 60 秒快照；每晚 23:45 結算＋狀態）
#   ./install_betfair_logger.sh --status
#   ./install_betfair_logger.sh --uninstall
#
# ⚠️ 要喺排程 checkout（/Users/imac/wongchoi-scheduler）入面行，plist 會指向呢個 checkout。
set -eu
SCRIPT_DIR="${0:A:h}"
PROJECT_ROOT="${SCRIPT_DIR:h:h:h:h}"
DEST_DIR="$HOME/Library/LaunchAgents"
UID_NUM="$(id -u)"
LABELS=(com.antigravity.au-wong-choi.betfair-snapshot com.antigravity.au-wong-choi.betfair-settle)
BF_ENV="$HOME/.wongchoi_betfair.env"

case "${1:-install}" in
  --status)
    for label in $LABELS; do
      echo "── $label ──"
      launchctl print "gui/$UID_NUM/$label" 2>/dev/null | grep -E "state =|last exit code|runs =" || echo "  (未安裝)"
    done
    exit 0 ;;
  --uninstall)
    for label in $LABELS; do
      launchctl bootout "gui/$UID_NUM" "$DEST_DIR/$label.plist" 2>/dev/null || true
      rm -f "$DEST_DIR/$label.plist"; echo "已移除 $label"
    done
    exit 0 ;;
  --check)
    [ -f "$BF_ENV" ] || { echo "❌ 冇 $BF_ENV"; exit 1; }
    perms="$(stat -f %Lp "$BF_ENV")"
    [ "$perms" = "600" ] || echo "⚠️  $BF_ENV 權限係 ${perms}，建議 chmod 600"
    set -a; source "$BF_ENV"; set +a
    exec /usr/bin/python3 "$SCRIPT_DIR/../au_betfair/au_betfair_logger.py" snapshot ;;
  install) ;;
  *) echo "用法：$0 [--check|--status|--uninstall]"; exit 2 ;;
esac

[ -f "$BF_ENV" ] || { echo "❌ 冇 $BF_ENV —— 先建立（見 au_betfair/betfair_client.py 頂部）"; exit 1; }
TZ_NAME="$(readlink /etc/localtime | sed 's#.*/zoneinfo/##')"
[ "$TZ_NAME" = "Australia/Sydney" ] || { echo "⚠️  本機時區 ${TZ_NAME}，23:45 唔係悉尼時間"; exit 1; }
mkdir -p "$DEST_DIR" "$SCRIPT_DIR/logs" "$SCRIPT_DIR/work"
for label in $LABELS; do
  dest="$DEST_DIR/$label.plist"
  sed -e "s#__SCRIPT_DIR__#$SCRIPT_DIR#g" -e "s#__PROJECT_ROOT__#$PROJECT_ROOT#g" \
    "$SCRIPT_DIR/launchd/$label.plist.template" > "$dest"
  plutil -lint "$dest" >/dev/null
  launchctl bootout "gui/$UID_NUM" "$dest" 2>/dev/null || true
  launchctl bootstrap "gui/$UID_NUM" "$dest"
  echo "已安裝 $label → $PROJECT_ROOT"
done
