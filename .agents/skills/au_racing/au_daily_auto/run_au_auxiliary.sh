#!/bin/zsh
# launchd 入口：獨立 healthcheck 同 Telegram command bot。
#
# 呢兩個 process 唔經 daily runner，但一樣要讀本機 AU data root 同 repo 外嘅
# Telegram credentials。集中喺 wrapper，避免 plist 複製一段難測、難搬機嘅 `zsh -lc`。
set -eu

TASK="${1:-}"
SCRIPT_DIR="${0:A:h}"
PROJECT_ROOT="${SCRIPT_DIR:h:h:h:h}"

# 中央旺財同四條 scheduler 共用呢個 dedicated production checkout。明確 export
# 令 Telegram approval/activation 唔使估 runtime 喺邊，亦唔會掂開發中嘅主 worktree。
: "${WC_PRIMARY_REPO_ROOT:=$PROJECT_ROOT}"
: "${WC_AU_PRODUCTION_ROOT:=$PROJECT_ROOT}"
: "${WC_HKJC_PRODUCTION_ROOT:=$PROJECT_ROOT}"
: "${WC_TENNIS_PRODUCTION_ROOT:=$PROJECT_ROOT}"
: "${WC_NBA_PRODUCTION_ROOT:=$PROJECT_ROOT}"
export WC_PRIMARY_REPO_ROOT WC_AU_PRODUCTION_ROOT WC_HKJC_PRODUCTION_ROOT
export WC_TENNIS_PRODUCTION_ROOT WC_NBA_PRODUCTION_ROOT

: "${WONGCHOI_AU_DATA_ROOT:=$HOME/WongChoiData/Wong Choi Horse Race Analysis/AU_Racing}"
# Google Drive 鏡像 2026-11-21 退役（Kelvin：冇人睇 Drive）。只有明確設定先鏡像。
export WONGCHOI_AU_DATA_ROOT
if [ -n "${WONGCHOI_AU_MIRROR_ROOT:-}" ]; then export WONGCHOI_AU_MIRROR_ROOT; fi

NOTIFY_ENV="$HOME/.wongchoi_notify.env"
[ -f "$NOTIFY_ENV" ] && source "$NOTIFY_ENV"

cd "$PROJECT_ROOT" || exit 1
case "$TASK" in
  healthcheck) exec /usr/bin/python3 "$SCRIPT_DIR/au_healthcheck.py" ;;
  # EXP-20261106-02 Betfair 市場走勢記錄（只讀，唔落注）。credentials 喺 repo 外 ~/.wongchoi_betfair.env。
  betfair-snapshot|betfair-settle)
    BF_ENV="$HOME/.wongchoi_betfair.env"
    [ -f "$BF_ENV" ] || { print -r -- "$BF_ENV 唔存在，Betfair 記錄器停用" >&2; exit 0; }
    set -a; source "$BF_ENV"; set +a
    BF="$SCRIPT_DIR/../au_betfair/au_betfair_logger.py"
    if [ "$TASK" = "betfair-snapshot" ]; then
      exec /usr/bin/python3 "$BF" snapshot
    fi
    /usr/bin/python3 "$BF" settle
    exec /usr/bin/python3 "$BF" status --output "$SCRIPT_DIR/work/au-betfair-log-status.json"
    ;;
  bot)         exec /usr/bin/python3 "$SCRIPT_DIR/au_telegram_bot.py" ;;
  # EXP-20261116-20：sportsbetform 手機逐駒分段，每日 04:30 抓前一至八日（隔 25 秒、非 200 即停、唔重試）。
  # 腳本自己只喺 03:00–09:00 開工，避開 22:00 evening job 同 10:00–16:00 refresh。
  # EXP-20261120-87：forward 抓完之後，同一個 job 用剩低嘅時間窗回填 08-05 → 11-05（09:00 即停、每晚最多 500 版）。
  # forward 抓取被擋（非 0）就唔回填。回填完齊先由 au_lpos_backfill.py 判一次並凍結。
  mobile-sectionals)
    MS="$SCRIPT_DIR/../au_wong_choi_auto/scripts"
    /usr/bin/python3 "$MS/au_mobile_sectionals.py" fetch --status "$SCRIPT_DIR/work/au-mobile-sectionals-fetch.json"
    /usr/bin/python3 "$MS/au_mobile_sectionals.py" fetch --backfill \
      --status "$SCRIPT_DIR/work/au-mobile-sectionals-backfill-fetch.json" || true
    exec /usr/bin/python3 "$MS/au_lpos_backfill.py" --notify --output "$SCRIPT_DIR/work/au-lpos-backfill-status.json" ;;
  *)
    print -r -- "用法：$0 healthcheck|bot|betfair-snapshot|betfair-settle|mobile-sectionals" >&2
    exit 2
    ;;
esac
