#!/usr/bin/env bash
# 備份去外置碟。你而家完全冇本機備份 —— 呢個係外置碟最有價值嘅用途。
#
#   ./備份.sh          備份 repo + 賽果資料
#   ./備份.sh --verify 只核對上次備份，唔複製
#
# 備份咩：
#   code（repo，連 git 歷史）  → 改壞咗可以還原
#   賽果／分析資料             → 呢啲重新抽唔返（Sportsbet 冇歷史 API）
#
# 唔備份咩，同點解：
#   .venv / node_modules      → 重新裝就有
#   .sportsbet_cache          → 30 日滾動 cache，過期無用
#   .claude/worktrees         → 只係分支副本，git 已經有
#   tennis_wc.db              → 1.76GB 每日重寫；ML 資料唔係唯一副本
set -uo pipefail
cd "$(dirname "$0")"

DISK="/Volumes/Kelvin Hardisk 1"
DEST="$DISK/Antigravity-Backup"

if [ ! -d "$DISK" ]; then
  echo "❌ 外置碟未掛載 —— 插返個掣先" >&2
  exit 1
fi

EXCLUDES=(
  --exclude '.venv/' --exclude '.venv-*/' --exclude 'node_modules/'
  --exclude '__pycache__/' --exclude '.pytest_cache/'
  --exclude '.sportsbet_cache/' --exclude '.ra_cache/'
  --exclude '.claude/worktrees/'
  --exclude '*.db-wal' --exclude '*.db-shm'
)

SOURCES=(
  "/Users/imac/Antigravity-repo"
  "/Users/imac/WongChoiData"
)

if [ "${1:-}" = "--verify" ]; then
  echo "── 核對上次備份 ──"
  for src in "${SOURCES[@]}"; do
    name=$(basename "$src")
    if [ ! -d "$DEST/$name" ]; then echo "  ❌ $name 未備份過"; continue; fi
    # A dry run that lists nothing means every file already matches.
    diff_count=$(rsync -an --itemize-changes "${EXCLUDES[@]}" "$src/" "$DEST/$name/" 2>/dev/null | grep -c '^[<>ch.]' || true)
    if [ "${diff_count:-0}" -eq 0 ]; then
      echo "  ✅ $name 同本機一致（$(du -sh "$DEST/$name" 2>/dev/null | cut -f1)）"
    else
      echo "  ⚠️  $name 有 $diff_count 個檔同本機唔同 —— 跑一次 ./備份.sh 更新"
    fi
  done
  exit 0
fi

mkdir -p "$DEST"
STATUS=0
for src in "${SOURCES[@]}"; do
  name=$(basename "$src")
  echo ""
  echo "── $name ──"
  if [ ! -d "$src" ]; then echo "  ⚠️  來源唔存在，跳過"; continue; fi
  # --delete keeps the backup an accurate mirror rather than an ever-growing
  # pile; without it a file you deliberately removed lives on forever and the
  # backup slowly stops resembling what you actually have.
  if rsync -a --delete "${EXCLUDES[@]}" "$src/" "$DEST/$name/" 2>&1 | tail -3; then
    echo "  ✅ $(du -sh "$DEST/$name" 2>/dev/null | cut -f1)"
  else
    echo "  ❌ 失敗"; STATUS=1
  fi
done

date '+%Y-%m-%d %H:%M:%S %Z' > "$DEST/.last_backup"
echo ""
echo "備份時間記錄喺 $DEST/.last_backup"
[ "$STATUS" -eq 0 ] && echo "✅ 完成" || echo "❌ 有部分失敗"
exit "$STATUS"
