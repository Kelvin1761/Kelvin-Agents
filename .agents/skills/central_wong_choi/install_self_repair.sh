#!/bin/zsh
# 安裝排程自動維修（每 30 分鐘）。預設裝 dry-run；--live 先真係修；--live --allow-llm-diagnosis 再加自動 Claude 診斷。
# --status／--uninstall 同 roi-summary 一樣。設計：docs/plans/2026-11-25-self-repair.md
set -eu

SKILL_DIR="${0:A:h}"
SCRIPT_DIR="$SKILL_DIR/scripts"
PROJECT_ROOT="${SKILL_DIR:h:h:h}"
LABEL="com.antigravity.central-wong-choi.self-repair"
DEST="$HOME/Library/LaunchAgents/$LABEL.plist"
UID_NUM="$(id -u)"

MODE_ARGS=""
for arg in "$@"; do
  case "$arg" in
    --status)
      launchctl print "gui/$UID_NUM/$LABEL" 2>/dev/null \
        | grep -E "state =|last exit code|program =|runs =|arguments" || print -r -- "(未安裝)"
      exit 0
      ;;
    --uninstall)
      launchctl bootout "gui/$UID_NUM" "$DEST" 2>/dev/null || true
      rm -f "$DEST"
      print -r -- "已移除 $LABEL"
      exit 0
      ;;
    --live) MODE_ARGS="${MODE_ARGS}<string>--live</string>" ;;
    --allow-llm-diagnosis) MODE_ARGS="${MODE_ARGS}<string>--allow-llm-diagnosis</string>" ;;
    *) print -u2 -r -- "唔識呢個參數：${arg}"; exit 2 ;;
  esac
done

mkdir -p "$HOME/Library/LaunchAgents" "$SCRIPT_DIR/logs"
chmod +x "$SCRIPT_DIR/run_self_repair.sh"
sed -e "s#__SCRIPT_DIR__#$SCRIPT_DIR#g" -e "s#__PROJECT_ROOT__#$PROJECT_ROOT#g" \
  -e "s#__MODE_ARGS__#${MODE_ARGS}#" \
  "$SKILL_DIR/launchd/$LABEL.plist.template" > "$DEST"
plutil -lint "$DEST" >/dev/null
chmod 644 "$DEST"
launchctl bootout "gui/$UID_NUM" "$DEST" 2>/dev/null || true
launchctl bootstrap "gui/$UID_NUM" "$DEST"
launchctl enable "gui/$UID_NUM/$LABEL"
print -r -- "已安裝 ${LABEL}：每 30 分鐘（${MODE_ARGS:-dry-run}）"
