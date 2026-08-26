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
exec 3>&1
exec >"$OUT" 2>&1
cleanup_output(){
  rc=$?
  trap - EXIT
  cat "$OUT" >&3 2>/dev/null || true
  rm -f "$OUT"
  exit "$rc"
}
trap cleanup_output EXIT

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
if   [ "$FREE_G" -lt 20 ]; then note_bad "內置碟只剩 ${FREE_G}GB —— 停止重型research/backfill，先做verified archive"
elif [ "$FREE_G" -lt 30 ]; then warn "內置碟剩 ${FREE_G}GB（低過中央旺財30GB HOT floor）"
else ok "內置碟剩 ${FREE_G}GB"; fi
if df -g | grep -q "Kelvin Hardisk"; then
  ok "外置碟已掛載（$(df -h | grep 'Kelvin Hardisk' | awk '{print $4}') 可用）"
else
  warn "外置碟未掛載 —— 封存／ML 資料攞唔到（唔影響每日流程）"
fi
STORAGE_JSON=$(WC_RESEARCH_REPO_ROOT="${WC_RESEARCH_REPO_ROOT:-/Users/imac/Antigravity-repo}" \
  "$PY" .agents/skills/central_wong_choi/scripts/central_wong_choi.py \
  storage --scan --json 2>/dev/null || true)
"$PY" - "$STORAGE_JSON" <<'PYEOF'
import json, sys
try:
    payload = json.loads(sys.argv[1])
except (IndexError, ValueError):
    print("  ⚠️  中央storage inventory unavailable")
    raise SystemExit
items = {item.get("name"): item for item in payload.get("inventory") or []}
for name, label in (
    ("tennis_db_backups", "Tennis DB snapshots"),
    ("au_archive", "AU archive"),
    ("hkjc_archive", "HKJC archive"),
):
    value = (items.get(name) or {}).get("gib")
    if value is not None:
        print(f"      {label}: {value:.2f} GiB")
cold = ((payload.get("tiers") or {}).get("cold") or {})
if not cold.get("configured"):
    print("  ⚠️  COLD Drive root未設定；外置碟目前只係一份copy，未可以批准刪本機原件")
elif cold.get("status") != "available":
    print(f"  ⚠️  COLD Drive不可用：{cold.get('error') or 'unknown'}")
PYEOF

# ── 排程 ──────────────────────────────────────────────────────────────────
hdr "自動化排程"
for f in "$HOME"/Library/LaunchAgents/com.antigravity.*.plist; do
  [ -e "$f" ] || continue
  lbl=$(basename "$f" .plist)
  short=${lbl#com.antigravity.}
  detail=$(launchctl print "gui/$(id -u)/$lbl" 2>/dev/null || true)
  if [ -z "$detail" ]; then
    note_bad "$short 冇載入 launchd"
  elif echo "$detail" | grep -q "(never exited)"; then
    ok "${short}（已載入，未到首次執行時間）"
  else
    st=$(echo "$detail" | sed -n 's/^[[:space:]]*last exit code = //p' | head -1)
    case "${st:-0}" in
      0) ok "$short" ;;
      *) warn "$short 上次退出碼 ${st}（睇下面詳情）" ;;
    esac
  fi
done

# ── 每個 Wong Choi 嘅資料時效 ─────────────────────────────────────────────
hdr "資料時效"
"$PY" - <<'PYEOF'
import os, sys, glob, json, sqlite3, time
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

# NBA off-season `dormant` is healthy. In season the immutable snapshot and
# reflector ledger are separate liveness/evidence signals.
nba_runs = []
for root in (".agents/skills/nba/nba_daily_auto/logs",
             "/Users/imac/Antigravity-repo/.agents/skills/nba/nba_daily_auto/logs"):
    nba_runs.extend(glob.glob(os.path.join(root, "run-*.json")))
if nba_runs:
    latest = max(set(nba_runs), key=os.path.getmtime)
    try:
        payload = json.load(open(latest, encoding="utf-8"))
        a = age_days(os.path.getmtime(latest))
        status = payload.get("status") or "unknown"
        target = payload.get("target_date") or "?"
        healthy = status in {"complete", "dormant", "archived", "already_archived", "ok"}
        mark = "✅" if healthy and a < 2 else "⚠️ "
        print(f"  {mark} NBA: 最新排程 {target} / {status}（{a:.1f} 日前）")
    except (OSError, ValueError) as exc:
        print(f"  ⚠️  NBA: 最新 run log 讀唔到（{exc.__class__.__name__}）")
else:
    print("  ⚠️  NBA: 未有 daily automation run log")

nba_db = next((candidate for candidate in (
    "nba_reflector.db",
    "/Users/imac/Antigravity-repo/nba_reflector.db",
) if os.path.exists(candidate)), None)
if nba_db:
    try:
        conn = sqlite3.connect(f"file:{nba_db}?mode=ro", uri=True)
        settled = conn.execute(
            "SELECT COUNT(*) FROM reflector_legs WHERE cleared IS NOT NULL"
        ).fetchone()[0]
        total = conn.execute("SELECT COUNT(*) FROM reflector_legs").fetchone()[0]
        conn.close()
        print(f"  ✅ NBA evidence ledger: {total} legs / {settled} settled")
    except (sqlite3.Error, OSError) as exc:
        print(f"  ⚠️  NBA evidence ledger 讀唔到（{exc.__class__.__name__}）")
else:
    print("  ⚠️  NBA evidence ledger 尚未建立（新季第一個 postgame 後產生）")
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

# ── 中央30日SLO／evidence provenance ──────────────────────────────────────
hdr "中央旺財 30日 SLO"
SLO_JSON=$("$PY" .agents/skills/central_wong_choi/scripts/central_wong_choi.py \
  slo --json 2>/dev/null)
SLO_RC=$?
if [ "$SLO_RC" -eq 0 ]; then
  ok "四線 run reliability 同 production provenance 達標（冇樣本會標 no_data）"
else
  note_bad "中央30日SLO未達標"
fi
"$PY" - "$SLO_JSON" <<'PYEOF'
import json, sys
try:
    payload = json.loads(sys.argv[1])
except (IndexError, ValueError):
    print("      SLO JSON unavailable")
    raise SystemExit
for name, value in (payload.get("domains") or {}).items():
    ratio = value.get("availability")
    shown = "no_data" if ratio is None else f"{ratio:.1%}"
    print(f"      {name.upper()}: {shown} · {value.get('slots', 0)} slots · {value.get('status')}")
provenance = ((payload.get("evidence") or {}).get("production_provenance") or {})
ratio = provenance.get("ratio")
print("      production provenance: " +
      ("no_data" if ratio is None else f"{ratio:.1%}") +
      f" · {provenance.get('production_decisions', 0)} decisions")
PYEOF

# ── 排程日誌有冇報錯 ─────────────────────────────────────────────────────
hdr "排程日誌（近 3 日嘅錯）"
found=0
LOG_SCAN=$("$PY" - <<'PYEOF'
import glob
import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

roots = (
    Path("/Users/imac/wongchoi-scheduler/.agents/skills/au_racing/au_daily_auto/logs"),
    Path(".agents/skills/hkjc_racing/hkjc_daily_auto/logs"),
    Path(".agents/skills/nba/nba_daily_auto/logs"),
    Path("tennis-wong-choi/data/logs"),
)
cutoff = datetime.now() - timedelta(days=3)
error_re = re.compile(
    r"traceback|fatal|Operation not permitted|unbound variable|❌ \[", re.I
)
stamp_re = re.compile(r"\[?(20\d\d-\d\d-\d\d[T ][0-9:]+(?:[+-][0-9:]+)?)")

# A successful newer mirror run resolves older best-effort File Provider noise.
mirror_step = None
run_files = sorted(
    glob.glob(str(roots[0] / "run-*.json")),
    key=os.path.getmtime,
    reverse=True,
)
for name in run_files[:30]:
    try:
        payload = json.loads(Path(name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        continue
    mirror_step = next(
        (step for step in reversed(payload.get("steps") or [])
         if step.get("step") == "mirror" and step.get("status") != "start"),
        None,
    )
    if mirror_step:
        break
mirror_ok = bool(mirror_step and mirror_step.get("status") == "ok")
if mirror_ok:
    print(
        "RECOVERED\tAU Drive mirror 最新 run 正常："
        f"copied {mirror_step.get('copied', 0)} / failed {mirror_step.get('failed', 0)}"
    )

for root in roots:
    if not root.is_dir():
        continue
    files = []
    for pattern in ("*.log", "*.err", "*.out"):
        files.extend(root.glob(pattern))
    for path in sorted(set(files)):
        if path.name in {"health.out", "health.err"}:
            continue
        try:
            if datetime.fromtimestamp(path.stat().st_mtime) < cutoff:
                continue
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        current_time = None
        errors = []
        for line in lines:
            match = stamp_re.search(line)
            if match:
                try:
                    current_time = datetime.fromisoformat(match.group(1)).replace(tzinfo=None)
                except ValueError:
                    current_time = None
            if not error_re.search(line):
                continue
            if current_time is not None and current_time < cutoff:
                continue
            lower = line.lower()
            resolved_mirror_noise = mirror_ok and (
                "[mirror]" in lower or "鏡像" in line or "mirror 最近狀態" in line
            )
            if resolved_mirror_noise:
                continue
            errors.append(line)
        if errors:
            print(f"WARN\t{path.name}\t{len(errors)}")
            for line in errors[-2:]:
                print("LINE\t" + line)
PYEOF
)
while IFS=$'\t' read -r kind arg count; do
  case "$kind" in
    RECOVERED) ok "$arg" ;;
    WARN) warn "$arg: $count 行錯誤"; found=1 ;;
    LINE) printf '        %s\n' "$arg" ;;
  esac
done <<< "$LOG_SCAN"
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
[ "$PROBLEMS" -gt 0 ] && exit 1 || exit 0
