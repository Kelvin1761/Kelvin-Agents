#!/usr/bin/env bash
# 一條命令，跑晒所有防線。唔使記其他嘢。
#
#   ./檢查.sh          全部
#   ./檢查.sh --quick  跳過單元測試（快，適合改完 code 即刻睇）
#
# 五道防線，由平到貴：
#   0. 清 bytecode cache  —— macOS 系統 Python 將 .pyc 放喺 ~/Library/Caches/
#      com.apple.python，而且淨係靠 (mtime, 檔案大小) 判斷要唔要重新編譯。改一個
#      權重由 0.08037 → 0.09037 位元組數一樣，同一秒內改完再跑 = 靜靜行舊 code。
#      呢個正正就係「A/B 結果同 baseline 一模一樣」嘅其中一個成因。
#   1. ruff              —— undefined name / 語法錯（第一次跑就捉到 generate_meeting_intel 一個 live NameError）
#   2. 評分 golden       —— 改一行 code 意外郁到第三個維度，逐匹馬印出嚟
#   3. 模型說明新鮮度    —— 文件同 live code 對唔上就紅燈
#   4. 數據合約          —— 欄位靜靜變空／變常數／單位飛咗
#   5. 單元測試          —— 原有 8 個 suite
set -uo pipefail
cd "$(dirname "$0")"
PY="${PYTHON_BIN:-python3}"
QUICK=0
[ "${1:-}" = "--quick" ] && QUICK=1

PASS=(); FAIL=(); SKIP=()
step() {
  local label="$1"; shift
  printf '\n\033[1m── %s\033[0m\n' "$label"
  if "$@"; then PASS+=("$label"); else FAIL+=("$label"); fi
}
soft_step() {   # 依賴資料根目錄；攞唔到就跳過，唔算失敗
  local label="$1"; shift
  printf '\n\033[1m── %s\033[0m\n' "$label"
  local out status
  out="$("$@" 2>&1)"; status=$?
  echo "$out"
  if [ $status -eq 2 ]; then SKIP+=("$label")
  elif [ $status -eq 0 ]; then PASS+=("$label")
  else FAIL+=("$label"); fi
}

printf '\n\033[1m── 0. 清走過期 bytecode\033[0m\n'
CACHE="$HOME/Library/Caches/com.apple.python$(pwd)"
rm -rf "$CACHE" 2>/dev/null
find . -name __pycache__ -type d -not -path "./.git/*" -exec rm -rf {} + 2>/dev/null
echo "   已清"
export PYTHONDONTWRITEBYTECODE=1

step "1. ruff（真係壞嘅嘢）" "$PY" -m ruff check --select F821,F811,F823,F701,F702,F706,F707,F811,E9 .

SHARED=.agents/skills/shared_racing/scripts
for p in au hkjc; do
  P=$(echo "$p" | tr "[:lower:]" "[:upper:]")
  step "2. 評分 golden — $P" "$PY" "$SHARED/golden_scoring.py" --platform "$p"
done
for p in au hkjc; do
  P=$(echo "$p" | tr "[:lower:]" "[:upper:]")
  step "3. 模型說明新鮮度 — $P" "$PY" "$SHARED/explain_model.py" --platform "$p" --check --no-corpus
done
for p in au hkjc; do
  P=$(echo "$p" | tr "[:lower:]" "[:upper:]")
  soft_step "4. 數據合約 — $P" "$PY" "$SHARED/data_contract.py" --platform "$p" --check --limit 60
done

if [ "$QUICK" = "1" ]; then
  SKIP+=("5. 單元測試（--quick 跳過）")
else
  step "5. 單元測試" ./run_tests.sh
fi

printf '\n\033[1m════════ 總結 ════════\033[0m\n'
for s in "${PASS[@]:-}"; do [ -n "$s" ] && printf '  \033[32m✅\033[0m %s\n' "$s"; done
for s in "${SKIP[@]:-}"; do [ -n "$s" ] && printf '  \033[33m➖\033[0m %s（跳過）\n' "$s"; done
for s in "${FAIL[@]:-}"; do [ -n "$s" ] && printf '  \033[31m❌\033[0m %s\n' "$s"; done
echo
if [ "${#FAIL[@]}" -gt 0 ]; then
  echo "有 ${#FAIL[@]} 項唔過。上面每一項都印咗點解同點修。"
  exit 1
fi
echo "全部過 ✅"
