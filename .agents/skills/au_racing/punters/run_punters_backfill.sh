#!/bin/zsh
# 分批慢慢補 Punters 段速：每批 200–300 請求，批之間休息 30–60 分鐘，凌晨 0–7 點唔跑。
# exit 2（被拒）即成個停 —— 唔好自動重試，要人睇。用法：
#   caffeinate -i ./run_punters_backfill.sh 2026-08-05
set -u
HERE="${0:A:h}"
SINCE="${1:-2026-08-05}"
export PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
batch=0
while true; do
  hour=$(date +%H)
  if (( 10#$hour < 7 )); then
    echo "$(date '+%F %T') 🌙 凌晨唔跑，瞓到 07:00"
    sleep $(( ( (7 - 10#$hour) * 3600 ) - 10#$(date +%M) * 60 + RANDOM % 900 ))
    continue
  fi
  batch=$((batch + 1))
  max=$((200 + RANDOM % 101))
  echo "$(date '+%F %T') ▶ 第 $batch 批（上限 $max 請求）"
  /usr/bin/python3 "$HERE/punters_backfill.py" --from "$SINCE" --max-requests "$max"
  rc=$?
  case $rc in
    0) echo "$(date '+%F %T') ✅ 全部補齊"; exit 0 ;;
    3) ;;
    *) echo "$(date '+%F %T') 🛑 rc=${rc}，停低等人睇"; exit $rc ;;
  esac
  rest=$((1800 + RANDOM % 1801))
  echo "$(date '+%F %T') 💤 休息 $((rest / 60)) 分鐘"
  sleep $rest
done
