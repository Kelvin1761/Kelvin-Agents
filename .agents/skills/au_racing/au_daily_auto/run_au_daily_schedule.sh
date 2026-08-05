#!/bin/zsh
# launchd 入口。launchd 唔會 source shell profile，所以 PATH 要喺呢度砌返。
#
# ⚠️ 一定要有 node/npx —— `Horse_Racing_Dashboard/deploy.sh` 靠 `npx wrangler@4.86.0`
#    發佈。launchd 預設 PATH 冇 nvm，冇咗呢段就會「分析成功、發佈靜靜失敗」。
#
# 2026-08-05 搬遷：AU 分析樹由 Google Drive 搬落本機硬碟。launchd spawn 出嚟嘅
# process 係另一個 TCC context，完全冇 CloudStorage 權限 —— 實測 preflight 一開工
# 就 `PermissionError: [Errno 1] Operation not permitted` 死咗。Tennis 2026-07-14
# 行過同一條路。呢度明確 export 兩個 root，唔靠 repo 裏面嗰個 gitignore 嘅
# dotfile（worktree／新 clone 都唔會有）：
#   WONGCHOI_AU_DATA_ROOT    本機 source of truth，引擎讀寫呢邊
#   WONGCHOI_AU_MIRROR_ROOT  Drive 鏡像，best-effort（launchd 底下寫唔入就 warn）
set -u

MODE="${1:-evening}"
shift 2>/dev/null || true

SCRIPT_DIR="${0:A:h}"
PROJECT_ROOT="${SCRIPT_DIR:h:h:h:h}"

: "${WONGCHOI_AU_DATA_ROOT:=$HOME/WongChoiData/Wong Choi Horse Race Analysis/AU_Racing}"
: "${WONGCHOI_AU_MIRROR_ROOT:=/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity/Wong Choi Horse Race Analysis/AU_Racing}"
export WONGCHOI_AU_DATA_ROOT WONGCHOI_AU_MIRROR_ROOT

# 本機 root 唔見咗就即刻死，唔好靜靜跌返 Drive 然後喺 preflight 出一個誤導訊息。
if [ ! -d "$WONGCHOI_AU_DATA_ROOT" ]; then
  print -r -- "FATAL: 本機 AU 資料根唔見咗：$WONGCHOI_AU_DATA_ROOT" >&2
  print -r -- "       （2026-08-05 由 Drive 搬過嚟。睇 au_daily_auto/README.md）" >&2
  exit 1
fi

# nvm 唔會喺 launchd 底下 load，所以直接揀最新一個裝好嘅 node bin。
NODE_BIN=""
for candidate in "$HOME"/.nvm/versions/node/*/bin(N); do
  NODE_BIN="$candidate"
done
[ -n "$NODE_BIN" ] && PATH="$NODE_BIN:$PATH"
PATH="/usr/local/bin:/opt/homebrew/bin:$PATH:/usr/bin:/bin:/usr/sbin:/sbin"
export PATH

cd "$PROJECT_ROOT" || exit 1

exec /usr/bin/python3 "$SCRIPT_DIR/au_daily_schedule.py" --mode "$MODE" "$@"
