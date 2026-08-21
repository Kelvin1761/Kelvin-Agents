#!/usr/bin/env bash
# 全 Wong Choi 營運健康檢查 —— 唔係查 code，係查「今日啲嘢有冇正常運作」。
#
#   ./健康.sh          睇晒四個 Wong Choi + 排程 + 磁碟
#   ./健康.sh --tg     順便推去 Telegram
#
# 同 ./檢查.sh 嘅分別：
#   檢查.sh  = code 有冇壞（ruff、golden、合約、單元測試）—— 交嘢之前跑
#   健康.sh  = 資料同自動化有冇斷（覆蓋率、時效、排程退出碼）—— 定期跑
set -uo pipefail
cd "$(dirname "$0")"
PY="${PYTHON_BIN:-python3}"
export PYTHONDONTWRITEBYTECODE=1
TG=0; [ "${1:-}" = "--tg" ] && TG=1

OUT=$(mktemp)
exec > >(tee "$OUT") 2>&1

hdr(){ printf '\n\033[1m── %s\033[0m\n' "$1"; }
ok(){  printf '  \033[32m✅\033[0m %s\n' "$1"; }
warn(){ printf '  \033[33m⚠️ \033[0m %s\n' "$1"; }
bad(){ printf '  \033[31m❌\033[0m %s\n' "$1"; }

PROBLEMS=0
note_bad(){ bad "$1"; PROBLEMS=$((PROBLEMS+1)); }

echo "Wong Choi 健康檢查  $(date '+%Y-%m-%d %H:%M')"

# ── 磁碟 ──────────────────────────────────────────────────────────────────
hdr "磁碟"
FREE_G=$(df -g / | tail -1 | awk '{print $4}')
if   [ "$FREE_G" -lt 5 ];  then note_bad "內置碟只剩 ${FREE_G}GB —— 排程會因為空間不足而 skip"
elif [ "$FREE_G" -lt 15 ]; then warn "內置碟剩 ${FREE_G}GB（偏低）"
else ok "內置碟剩 ${FREE_G}GB"; fi
if df -g | grep -q "Kelvin Hardisk"; then
  ok "外置碟已掛載（$(df -h | grep 'Kelvin Hardisk' | awk '{print $4}') 可用）"
else
  warn "外置碟未掛載 —— 封存／ML 資料攞唔到（唔影響每日流程）"
fi

# ── 排程 ──────────────────────────────────────────────────────────────────
hdr "自動化排程"
for f in "$HOME"/Library/LaunchAgents/com.antigravity.*.plist; do
  [ -e "$f" ] || continue
  lbl=$(basename "$f" .plist)
  short=${lbl#com.antigravity.}
  st=$(launchctl list 2>/dev/null | grep -w "$lbl" | awk '{print $2}')
  case "${st:-missing}" in
    0)       ok "$short" ;;
    missing) note_bad "$short 冇載入 launchd" ;;
    *)       warn "$short 上次退出碼 $st（睇下面詳情）" ;;
  esac
done

# ── 每個 Wong Choi 嘅資料時效 ─────────────────────────────────────────────
hdr "資料時效"
"$PY" - <<'PYEOF'
import os, sys, glob, sqlite3, time
from datetime import datetime, timedelta, timezone
sys.path.insert(0, os.getcwd())

def age_days(ts):
    return (time.time() - ts) / 86400

def newest(pattern):
    files = glob.glob(pattern)
    return max((os.path.getmtime(f) for f in files), default=None)

try:
    from wongchoi_paths import AU_RACING, HK_RACING
except Exception as exc:
    print(f"  ❌ 讀唔到路徑設定：{exc}"); raise SystemExit

# AU: meetings are near-daily, so a multi-day gap is a real outage.
sys.path.insert(0, os.path.join(os.getcwd(), ".agents/skills/shared_racing/scripts"))
from corpus_paths import meeting_dirs   # noqa: E402  (Archive/ holds half the corpus)

for label, root, stale_days in (("AU", AU_RACING, 3), ("HKJC", HK_RACING, 21)):
    try:
        meetings = [d.name for d in sorted(meeting_dirs(root), key=lambda p: p.name)]
    except OSError as exc:
        print(f"  ❌ {label} 資料根目錄讀唔到：{exc.__class__.__name__}"); continue
    if not meetings:
        print(f"  ❌ {label} 一個場次都冇"); continue
    last = meetings[-1]
    last_dir = next((d for d in meeting_dirs(root) if d.name == last), None)
    scored = len(glob.glob(os.path.join(str(last_dir), "Race_*_Logic.json"))) if last_dir else 0
    try:
        d = datetime.strptime(last[:10], "%Y-%m-%d")
        gap = (datetime.now() - d).days
    except ValueError:
        gap = None
    mark = "✅" if (gap is not None and gap <= stale_days) else "⚠️ "
    print(f"  {mark} {label}: 最新場次 {last}（{gap} 日前），已評分 {scored} 場，"
          f"語料庫共 {len(meetings)} 個場次")

# Tennis: the DB is written every day, so its mtime IS the liveness signal.
# Tennis only exists in the main repo — this script also runs from the AU
# scheduler worktree, where a relative path would wrongly report it missing.
db = next((c for c in ("tennis-wong-choi/tennis_wc.db",
                       "/Users/imac/Antigravity-repo/tennis-wong-choi/tennis_wc.db")
           if os.path.exists(c)), None)
if db:
    a = age_days(os.path.getmtime(db))
    mark = "✅" if a < 2 else "⚠️ "
    size = os.path.getsize(db) / 1073741824
    print(f"  {mark} Tennis: DB {size:.2f}GB，{a:.1f} 日前寫過")
else:
    print("  ⚠️  Tennis: 呢個 checkout 冇 tennis_wc.db（Tennis 只住喺主 repo）")
PYEOF

# ── 數據合約 ─────────────────────────────────────────────────────────────
hdr "數據合約（欄位有冇靜靜變空／變常數）"
for p in au hkjc; do
  P=$(echo "$p" | tr '[:lower:]' '[:upper:]')
  o=$("$PY" .agents/skills/shared_racing/scripts/data_contract.py --platform "$p" --check --limit 60 2>&1)
  s=$?
  if   [ $s -eq 0 ]; then ok "$P $(echo "$o" | grep -E '^樣本' | head -1)"
  elif [ $s -eq 2 ]; then warn "$P 攞唔到語料庫（跳過）"
  else note_bad "$P 有欄位唔合格"; echo "$o" | sed -n '/唔合格/,/^$/p' | sed 's/^/      /'; fi
done

# ── 排程日誌有冇報錯 ─────────────────────────────────────────────────────
hdr "排程日誌（近 3 日嘅錯）"
found=0
for L in /Users/imac/wongchoi-scheduler/.agents/skills/au_racing/au_daily_auto/logs \
         .agents/skills/hkjc_racing/hkjc_daily_auto/logs \
         tennis-wong-choi/data/logs; do
  [ -d "$L" ] || continue
  while IFS= read -r f; do
    n=$(grep -icE "traceback|fatal|Operation not permitted|unbound variable|❌ \[" "$f" 2>/dev/null | head -1)
    n=${n:-0}
    if [ "$n" -gt 0 ]; then
      warn "$(basename "$f"): $n 行錯誤"
      grep -iE "traceback|fatal|Operation not permitted|unbound variable|❌ \[" "$f" 2>/dev/null | tail -2 | sed 's/^/        /'
      found=1
    fi
    # Skip our own output: last week's report quotes last week's errors, which
    # would resurface here forever as if they were new.
  done < <(find "$L" \( -name "*.log" -o -name "*.err" -o -name "*.out" \) \
             ! -name "health.out" ! -name "health.err" -mtime -3 2>/dev/null)
done
[ "$found" = "0" ] && ok "近 3 日嘅日誌冇 traceback / 權限錯誤 / 排程階段失敗"

# ── 總結 ─────────────────────────────────────────────────────────────────
printf '\n\033[1m════════ 總結 ════════\033[0m\n'
if [ "$PROBLEMS" -gt 0 ]; then
  printf '  \033[31m%s 項要處理\033[0m\n\n' "$PROBLEMS"
else
  printf '  \033[32m冇嚴重問題\033[0m（⚠️ 嗰啲值得睇，但唔急）\n\n'
fi

if [ "$TG" = "1" ]; then
  "$PY" .agents/skills/shared_racing/scripts/racing_telegram.py \
    --message-file "$OUT" >/dev/null 2>&1 && echo "已推去 Telegram"
fi
rm -f "$OUT"
[ "$PROBLEMS" -gt 0 ] && exit 1 || exit 0
