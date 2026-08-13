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

# 通知設定。⚠️ 住喺 repo 外面，所以永遠唔會意外 commit 咗個 token 出去。
# 內容例：
#   export WC_NOTIFY_TELEGRAM_TOKEN=123456:AA...
#   export WC_NOTIFY_TELEGRAM_CHAT=123456789
#   export WC_NOTIFY_ONLY_PROBLEMS=1        # 想淨係出事先出聲就解除註解
NOTIFY_ENV="$HOME/.wongchoi_notify.env"
[ -f "$NOTIFY_ENV" ] && source "$NOTIFY_ENV"

cd "$PROJECT_ROOT" || exit 1

# ── 追上最新模型 ────────────────────────────────────────────────────────────
# ⚠️ 呢個 checkout 專屬排程，冇人喺度改嘢，所以 fast-forward 係安全嘅。
# 點解要有：2026-08-09 實測，共用嗰個 repo 喺我 commit 完幾分鐘之後已經俾另一個
# session 換咗去 tennis 分支。嗰次啱啱好仍然含住所有 AU 修正 —— 但一條舊分支就
# 會靜靜咁用舊模型評分，而冇任何嘢會投訴。
#
# `sb_archive_meeting_ids.json` 係已追蹤但又會俾 run 寫入，所以 ff 會被拒。
# ⚠️ 一度用 `git checkout --` 還原佢，並且註解寫「掉咗唔會錯」—— 嗰句係錯嘅。
# 2026-08-12 實測：咁樣每次 run 開頭都抹走上一次 run 寫入嘅 meeting ID，於是
# 10:00 覆核五個場次全部報「對應表冇呢個場次」，退出馬同場地變化一個都覆核唔到。
# 覆盤路徑會由索引頁重新推導，但覆核路徑唔會，佢直接放棄。
# 而家改成：影一份本機版 → checkout 讓 ff 過 → 做並集合併返去。
if [ -z "${WC_AU_NO_SELF_UPDATE:-}" ]; then
  MAPPING=".agents/skills/au_racing/data/sb_archive_meeting_ids.json"
  MAP_BAK=""
  WC_AU_CODE_UPDATE_WARNING=""
  export WC_AU_CODE_UPDATE_WARNING

  # 先判斷 branch 關係，先至掂會由 live run 寫入嘅 mapping。production branch
  # 分叉時 fast-forward 必定失敗；嗰陣 checkout mapping 只會製造中途 crash
  # 抹走上一個 run 新增 meeting ID 嘅窗口，完全冇更新收益。
  if ! git fetch --quiet origin 2>/dev/null; then
    WC_AU_CODE_UPDATE_WARNING="git fetch 失敗 —— 未能核實 production code 係咪最新，今次用現有版本"
  else
    AHEAD=0
    BEHIND=0
    COUNTS="$(git rev-list --left-right --count HEAD...origin/main 2>/dev/null || true)"
    if [ -n "$COUNTS" ]; then
      read -r AHEAD BEHIND <<< "$COUNTS"
    fi
    if [ "$BEHIND" -eq 0 ] 2>/dev/null; then
      : # 已包含 origin/main；local commits 可以照留。
    elif [ "$AHEAD" -gt 0 ] 2>/dev/null; then
      WC_AU_CODE_UPDATE_WARNING="production branch 已分叉（ahead $AHEAD / behind $BEHIND），無法自動 fast-forward；今次用現有版本，要人手合併 origin/main"
    else
      MAP_BAK="$(mktemp -t wc_mapping)"
      cp "$MAPPING" "$MAP_BAK" 2>/dev/null || true

      restore_mapping() {
        if [ -n "${MAP_BAK:-}" ] && [ -s "$MAP_BAK" ]; then
          /usr/bin/python3 "$SCRIPT_DIR/merge_mapping.py" "$MAPPING" "$MAP_BAK" \
            >/dev/null 2>&1 || cp "$MAP_BAK" "$MAPPING"
          rm -f "$MAP_BAK"
          MAP_BAK=""
        fi
      }
      trap restore_mapping EXIT HUP INT TERM

      git checkout --quiet -- "$MAPPING" 2>/dev/null || true
      if git merge --ff-only --quiet origin/main 2>/dev/null; then
        if [ -s "$MAP_BAK" ] && ! /usr/bin/python3 "$SCRIPT_DIR/merge_mapping.py" "$MAPPING" "$MAP_BAK"; then
          cp "$MAP_BAK" "$MAPPING"
          print -r -- "FATAL: 更新 code 後合併 meeting-ID mapping 失敗；已還原本機 mapping，今次唔開工" >&2
          exit 1
        fi
        rm -f "$MAP_BAK"
        MAP_BAK=""
      else
        restore_mapping
        WC_AU_CODE_UPDATE_WARNING="fast-forward origin/main 失敗 —— 今次用現有版本（工作區可能有其他改動）"
      fi
      trap - EXIT HUP INT TERM
    fi
  fi
  if [ -n "$WC_AU_CODE_UPDATE_WARNING" ]; then
    print -r -- "⚠️ $WC_AU_CODE_UPDATE_WARNING" >&2
  fi
  print -r -- "▶ 版本 $(git rev-parse --short HEAD) ($(git rev-parse --abbrev-ref HEAD))"
fi

exec /usr/bin/python3 "$SCRIPT_DIR/au_daily_schedule.py" --mode "$MODE" "$@"
