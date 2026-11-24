#!/bin/zsh
# 異地加密備份（系統升級第 2 項）：每日 run；星期日（悉尼）再做還原演練。失敗推 primary Telegram。
set -u
ROOT="${0:A:h:h:h:h:h}"
cd "$ROOT" || exit 2
print -r -- "== $(date '+%F %T') offsite backup"
/usr/bin/python3 .agents/scripts/offsite_backup.py run --notify || exit $?
if [ "$(date +%u)" = "7" ]; then
  print -r -- "== $(date '+%F %T') restore drill"
  /usr/bin/python3 .agents/scripts/offsite_backup.py drill --groups 3 --notify || exit $?
fi
