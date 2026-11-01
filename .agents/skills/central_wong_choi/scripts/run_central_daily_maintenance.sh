#!/bin/zsh
set -eu

SCRIPT_DIR="${0:A:h}"
PROJECT_ROOT="${SCRIPT_DIR:h:h:h:h}"

: "${WC_PRIMARY_REPO_ROOT:=$PROJECT_ROOT}"
: "${WONGCHOI_CONTROL_STATE_ROOT:=$HOME/WongChoiData/WongChoiControl}"
: "${WC_WARM_ARCHIVE_ROOT:=/Volumes/Kelvin Hardisk 1/WongChoi-Archive}"
export WC_PRIMARY_REPO_ROOT WONGCHOI_CONTROL_STATE_ROOT WC_WARM_ARCHIVE_ROOT

for env_file in "$HOME/.wongchoi_notify.env" "$HOME/.wongchoi_cloudflare.env"; do
  [ -f "$env_file" ] && source "$env_file"
done

if [ -z "${WC_COLD_MIRROR_ROOT:-}" ] && [ -f "$HOME/.wongchoi_cold_mirror_root" ]; then
  IFS= read -r WC_COLD_MIRROR_ROOT < "$HOME/.wongchoi_cold_mirror_root" || true
  export WC_COLD_MIRROR_ROOT
fi

export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && source "$NVM_DIR/nvm.sh"

cd "$PROJECT_ROOT"

# 追上 origin/main。⚠️ 五個排程共用同一個 worktree，而 2026-09-09 之前**只有 AU
# 個 wrapper 會 ff** —— 其餘四個更新 code 全靠 AU 啱啱好有開工帶挈。AU 一停，
# 佢哋就無限期跑舊 code 而冇任何嘢會投訴。失敗唔會阻開工（見個 script 頭）。
/usr/bin/python3 "$PROJECT_ROOT/.agents/scripts/wongchoi_self_update.py" "$PROJECT_ROOT" || true
rc=0
/usr/bin/python3 "$SCRIPT_DIR/central_daily_maintenance.py" || rc=$?

# 備份做完先搬：14 日以上、已入 AU Archive/ 嘅場次快照搬去外置碟（抄、逐檔 sha256
# 核對、寫標記，最後先刪本機；reader 經 wongchoi_paths.prediction_snapshot_dir 跟標記）。
# 外置碟冇掛載就自己跳過。失敗唔影響 durability 嘅退出碼，健康.sh 會報。
/usr/bin/python3 "$PROJECT_ROOT/.agents/scripts/offload_prediction_snapshots.py" \
  --time-budget 900 || true

# 備份做完先至壓縮：3 日以上嘅資料檔轉 APFS 透明壓縮（路徑、內容、mtime 唔變，
# 讀檔 code 唔使改）。2026-11-01 內置碟淨 4.8GB —— snapshot 每次成份複製，
# 一個月加 7GB。夠鐘就停、下次續做；失敗唔影響 durability 嘅退出碼。
/usr/bin/python3 "$PROJECT_ROOT/.agents/scripts/compress_data_root.py" \
  "$HOME/WongChoiData" --time-budget 1500 || true
exit $rc
