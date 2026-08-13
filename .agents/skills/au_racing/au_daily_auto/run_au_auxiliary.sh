#!/bin/zsh
# launchd 入口：獨立 healthcheck 同 Telegram command bot。
#
# 呢兩個 process 唔經 daily runner，但一樣要讀本機 AU data root 同 repo 外嘅
# Telegram credentials。集中喺 wrapper，避免 plist 複製一段難測、難搬機嘅 `zsh -lc`。
set -eu

TASK="${1:-}"
SCRIPT_DIR="${0:A:h}"
PROJECT_ROOT="${SCRIPT_DIR:h:h:h:h}"

: "${WONGCHOI_AU_DATA_ROOT:=$HOME/WongChoiData/Wong Choi Horse Race Analysis/AU_Racing}"
: "${WONGCHOI_AU_MIRROR_ROOT:=/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity/Wong Choi Horse Race Analysis/AU_Racing}"
export WONGCHOI_AU_DATA_ROOT WONGCHOI_AU_MIRROR_ROOT

NOTIFY_ENV="$HOME/.wongchoi_notify.env"
[ -f "$NOTIFY_ENV" ] && source "$NOTIFY_ENV"

cd "$PROJECT_ROOT" || exit 1
case "$TASK" in
  healthcheck) exec /usr/bin/python3 "$SCRIPT_DIR/au_healthcheck.py" ;;
  bot)         exec /usr/bin/python3 "$SCRIPT_DIR/au_telegram_bot.py" ;;
  *)
    print -r -- "用法：$0 healthcheck|bot" >&2
    exit 2
    ;;
esac
