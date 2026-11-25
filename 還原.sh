#!/bin/zsh
# 新機（或者壞機之後）還原成個 Wong Choi。詳細步驟同點解：docs/RESTORE.md
#
#   ./還原.sh            照步驟做；做過嘅步驟會跳過（可以重複跑）
#   ./還原.sh --check    只檢查前提，唔郁任何嘢
#
# 前提（腳本會逐個檢查，唔夠就停低講你知做咩）：
#   1. Homebrew（https://brew.sh）同 Xcode Command Line Tools（xcode-select --install）
#   2. GitHub 登入（gh auth login）—— 拎 code
#   3. rclone 授權咗 Google Drive，remote 名叫 gdrive（rclone config create gdrive drive）
#   4. 加密鑰匙：喺 Apple「密碼」app 嘅 wongchoi-offsite 抄出嚟，腳本會叫你貼
#
# 原則：唔覆蓋任何現有檔；資料由 Google Drive 加密備份還原（offsite_backup.py），code 由 GitHub。
set -eu

REPO_URL="https://github.com/Kelvin1761/Kelvin-Agents.git"
REPO="$HOME/Antigravity-repo"
SCHED="$HOME/wongchoi-scheduler"
DATA="$HOME/WongChoiData"
DISK="/Volumes/Kelvin Hardisk 1"
KEY="$HOME/.wongchoi_offsite.key"
CFG="$HOME/.wongchoi_offsite.json"
REMOTE="${WC_RESTORE_REMOTE:-gdrive:WongChoiBackup}"
CHECK_ONLY=0
[ "${1:-}" = "--check" ] && CHECK_ONLY=1

step() { print -r -- ""; print -r -- "== $1"; }
need() { command -v "$1" >/dev/null 2>&1; }
stop() { print -r -- "❌ $1"; exit 1; }

step "1. 前提"
need brew || stop "未裝 Homebrew：去 https://brew.sh 跟指示裝，再重跑"
need git || stop "未有 git：行 xcode-select --install"
[ -x /usr/bin/python3 ] || stop "未有 /usr/bin/python3：行 xcode-select --install"
for tool in rclone zstd node gh; do
  if ! need "$tool"; then
    [ $CHECK_ONLY = 1 ] && { print -r -- "⚠️  未裝 $tool"; continue; }
    print -r -- "裝 $tool …"; brew install "$tool"
  fi
done
if need rclone && ! rclone lsd gdrive: >/dev/null 2>&1; then
  print -r -- "⚠️  rclone 未授權 Google Drive。行：rclone config create gdrive drive（會開瀏覽器，用你嘅 Google 帳戶登入），再重跑"
  [ $CHECK_ONLY = 1 ] || exit 1
fi
[ $CHECK_ONLY = 1 ] && { print -r -- "（--check：前提檢查完，冇郁嘢）"; exit 0; }

step "2. Code（GitHub）"
if [ ! -d "$REPO/.git" ]; then
  gh auth status >/dev/null 2>&1 || stop "未登入 GitHub：行 gh auth login，再重跑"
  git clone "$REPO_URL" "$REPO"
else
  print -r -- "已有 ${REPO}（跳過）"
fi
git -C "$REPO" fetch -q origin
if [ ! -d "$SCHED" ]; then
  # 生產排程行呢個 checkout（git worktree，self-update 會自己追 main）
  git -C "$REPO" worktree add "$SCHED" -b "codex-production-main-$(date +%Y%m%d)" origin/main
else
  print -r -- "已有 ${SCHED}（跳過）"
fi

step "3. 加密鑰匙同備份設定"
if [ ! -s "$KEY" ]; then
  print -r -- "去 Apple「密碼」app 搵 wongchoi-offsite，複製個密碼，貼喺度（唔會顯示）再按 Enter："
  read -rs PASTED; print
  [ -n "$PASTED" ] || stop "冇貼到鑰匙"
  umask 077; print -r -- "$PASTED" > "$KEY"; chmod 600 "$KEY"; unset PASTED
fi
[ -f "$CFG" ] || /usr/bin/python3 "$REPO/.agents/scripts/offsite_backup.py" init --backend "rclone:$REMOTE" --key-file "$KEY"

step "4. 由 Google Drive 還原（解密、核 sha256）"
if mount | grep -q "on $DISK "; then STAGE="$DISK/WongChoi-Archive/restore-$(date +%Y%m%d)"
else STAGE="$HOME/WongChoiRestore-$(date +%Y%m%d)"; fi
if [ ! -d "$STAGE" ] || [ -z "$(ls -A "$STAGE" 2>/dev/null)" ]; then
  df -h "${STAGE:h}" | tail -1
  print -r -- "還原去 ${STAGE}（全部大約 30GB，要等一陣）…"
  /usr/bin/python3 "$REPO/.agents/scripts/offsite_backup.py" restore --dest "$STAGE"
else
  print -r -- "$STAGE 已經有嘢（跳過下載）"
fi

step "5. 放返原位（唔覆蓋現有檔）"
mkdir -p "$DATA"
[ -d "$STAGE/data" ] && rsync -a --ignore-existing "$STAGE/data/" "$DATA/"
/usr/bin/python3 "$REPO/.agents/scripts/offsite_backup.py" place --from "$STAGE"
if [ -f "$STAGE/tennis/tennis-db/tennis_wc.db" ] && [ ! -f "$REPO/tennis-wong-choi/tennis_wc.db" ]; then
  cp -p "$STAGE/tennis/tennis-db/tennis_wc.db" "$REPO/tennis-wong-choi/tennis_wc.db"
fi
if mount | grep -q "on $DISK "; then ARCH="$DISK/WongChoi-Archive"
else ARCH="$HOME/WongChoiArchive"; print -r -- "⚠️  外置碟冇插：外置碟資料放咗去 ${ARCH}（之後插碟再搬過去）"; fi
mkdir -p "$ARCH"
for pair in "betfair-log:betfair-market-log" "pred-snapshots:prediction-snapshots" \
            "gdrive-export:gdrive-export-20261121" "hkjc-history:hkjc-history" "archive-tennis:tennis"; do
  src="${pair%%:*}"; dst="${pair#*:}"
  [ -d "$STAGE/$src" ] && rsync -a --ignore-existing "$STAGE/$src/" "$ARCH/$dst/"
done
# plist 入面寫死咗舊機嘅 home；新機用戶名唔同就換
if [ "$HOME" != "/Users/imac" ]; then
  for f in "$HOME"/Library/LaunchAgents/com.antigravity.*.plist; do
    [ -f "$f" ] && sed -i '' "s#/Users/imac#$HOME#g" "$f"
  done
fi

step "6. Python／Node 環境"
[ -x "$REPO/tennis-wong-choi/.venv/bin/python" ] || {
  /usr/bin/python3 -m venv "$REPO/tennis-wong-choi/.venv"
  "$REPO/tennis-wong-choi/.venv/bin/pip" install -q -e "$REPO/tennis-wong-choi"
}
/usr/bin/python3 -m pip install -q --user -r "$REPO/requirements.txt" || print -r -- "⚠️  requirements.txt 有部分裝唔到，睇 SETUP.md"
(cd "$REPO/Horse_Racing_Dashboard" && npm ci --silent) || print -r -- "⚠️  dashboard npm ci 失敗，睇 SETUP.md"

step "7. 排程（launchd）"
for f in "$HOME"/Library/LaunchAgents/com.antigravity.*.plist; do
  [ -f "$f" ] || continue
  label="$(basename "$f" .plist)"
  launchctl print "gui/$(id -u)/$label" >/dev/null 2>&1 && continue
  launchctl bootstrap "gui/$(id -u)" "$f" && print -r -- "已載入 $label"
done
print -r -- "（research-review 係暫停咗嘅，plist 喺 $DATA/WongChoiControl/paused-launchd/，唔會自動載入）"

step "8. 驗證"
(cd "$SCHED" && ./健康.sh) || true
print -r -- ""
print -r -- "✅ 還原完成。仲要人手做嘅：Full Disk Access（系統設定 → 私隱與安全性 → 完整磁碟取用，加 /bin/zsh 同 /usr/bin/python3）、"
print -r -- "   Cloudflare 登入（cd $REPO/Horse_Racing_Dashboard && npx wrangler login）—— 詳見 docs/RESTORE.md"
